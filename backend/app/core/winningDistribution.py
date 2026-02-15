from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorClient,AsyncIOMotorDatabase
import asyncio
from schemas.gameTransactionSchema import GameTransactionInDB
from schemas.winningDistributionSchema import WinningDistributionInDB
from typing import List,Optional
from services.game_service import get_undistributed_games
from services.user_service import get_users_by_phones,get_user_by_phone
from models.user import UserInDB
from pymongo.errors import PyMongoError
from core.config import settings
from core.db import get_db, get_client
from collections import defaultdict
from schemas.creditBalance import CreditBalanceInDB
from schemas.transactionHistory import TransactionHistoryCreate
from datetime import datetime


async def calculate_winning_distribution(
    db_client: AsyncIOMotorClient, game_id:str= None,redistribute: Optional[bool] = False,is_production: bool = False
) -> List[WinningDistributionInDB]:
    """
    Calculate and store winning distributions for undistributed games atomically.
    Returns the list of inserted distributions.
    """
    db_name = settings.MONGODB_NAME
    distribution_collection = db_client[db_name].WinningDistributions
    game_collection = db_client[db_name].gametransactions

    print(f"distributions  for game {game_id}, is-redistribute -> {redistribute}")

    if(not redistribute and game_id):
        distributions = await distribution_collection.find({"gameId": game_id}).to_list(length=None)
        if distributions:
            print(f"distributions already found for game {game_id}")
            return distributions
        
    undistributed_games = []

    if(game_id and redistribute):
        isDeposited = await distribution_collection.find_one({"gameId": game_id,"deposited":True})
        if isDeposited:
            #this should reverse the transaction and redistribute
            raise Exception("Distribution already deposited.")
        else:
            await distribution_collection.delete_many({"gameId": game_id})
        
        game = await game_collection.find_one({"game_id": game_id})
        if not game:
            raise Exception("Game not found.")
        undistributed_games.append(game)
    else:
        undistributed_games = await get_undistributed_games(game_collection,game_id)
        if not undistributed_games or len(undistributed_games) == 0:
            print('found no undistributed games ...')
            raise Exception("No undistributed games found.")
    
    print(f"undistributed games count: {len(undistributed_games)}")
    all_inserted_distributions = []

    if is_production:
        async with await db_client.start_session() as session:
            for game in undistributed_games:
                if not (game.game_completed and not game.game_distributed):
                    print(f"Game {game.game_id} is not completed or already distributed.")
                    continue

                try:
                    async with session.start_transaction():
                        distributions = await distribute_winning(game, db_client[db_name])
                        if not distributions:
                            print(f"distributions not found for Game {game.game_id}")
                            continue

                        await distribution_collection.insert_many(
                            [d.model_dump() for d in distributions],
                            session=session
                        )

                        await game_collection.update_one(
                            {"game_id": game.game_id},
                            {"$set": {"game_distributed": True}},
                            session=session
                        )

                        all_inserted_distributions.extend(distributions)

                except PyMongoError as e:
                    print(f"distribution failed for game {game.game_id}: {e}")
                    continue
    else:
        for game in undistributed_games:
            if not (game.game_completed and not game.game_distributed):
                print(f"Game {game.game_id} is not completed or already distributed.")
                continue

            try:
                distributions = await distribute_winning(game, db_client[db_name])
                if not distributions:
                    print(f"distributions not found for Game {game.game_id}")
                    continue

                await distribution_collection.insert_many(
                    [d.model_dump() for d in distributions]
                )

                await game_collection.update_one(
                    {"game_id": game.game_id},
                    {"$set": {"game_distributed": True}}
                )

                all_inserted_distributions.extend(distributions)

            except PyMongoError as e:
                print(f"distribution failed for game {game.game_id}: {e}")
                continue

    print("done game distribution for games ...")
    return all_inserted_distributions

async def distribute_winning(game: GameTransactionInDB, db) -> List[WinningDistributionInDB]: # Removed Depends for broader use
    """
    This method will perform the actual game winning distribution to agents and admins.
    """
    if not game.players or len(game.players) == 0:
        print(f"Game {game.game_id} has no players.")
        return [] # Return empty list instead of None for type consistency

    # Get all player objects to get their agents and admins
    game_players_details: List[UserInDB] = await get_users_by_phones(db.users, game.players)
    if not game_players_details:
        print(f"Could not fetch player details for game {game.game_id}.")
        return []
    print(f"game players details count: {len(game_players_details)} for game {game.game_id}")

    total_distributable_to_uplines: float = game.total_winning - game.player_winning
    if total_distributable_to_uplines <= 0:
        print(f"No distributable amount for uplines in game {game.game_id}.")
        return []
    
    print(f"total distributions for game{game.game_id}: {total_distributable_to_uplines}")
    total_players_in_game: int = len(game.players)
    print(f'total players in game {game.game_id}: {total_players_in_game}')
    # Get distinct (agentId, adminId) pairs from the players in the game
    # We only care about players who actually have an agent and admin assigned for this distribution logic
    # distinct_agent_admin_pairs = list(
    #     {
    #         (player.agentId, player.adminId)
    #         for player in game_players_details
    #         if player.agentId and player.adminId # Ensure they exist
    #     }
    # )

    falsy_values = {None, '', '0', 0, 'null', 'None','system'}
    
    # distinct_agent_admin_pairs = list({
    # (
    #     'system' if  player.agentId in falsy_values and player.adminId in falsy_values else player.agentId,
    #     'system' if  player.agentId in falsy_values and player.adminId in falsy_values else player.adminId,
    # )
    # for player in game_players_details
    # })

    distinct_agent_admin_pairs = list({
    (
        player.agentId if player.agentId not in falsy_values else 'system',
        player.adminId if player.adminId not in falsy_values else 'system',
    )

    for player in game_players_details
    
    })


    print(f"distinct agent admin pairs count: {len(distinct_agent_admin_pairs)} for game {game.game_id}")
    print(distinct_agent_admin_pairs)
    distributions: List[WinningDistributionInDB] = []
    current_time = game.date

    # Common details for each distribution record from this game
    common_game_data_for_record = {
        "gameId": game.game_id,
        "date": current_time,
        "totalPlayers": total_players_in_game,
        "betAmount": game.bet_amount, # Or game.total_bet_amount if available and more suitable
        "totalWinning": game.total_winning,
        "distributable": total_distributable_to_uplines, # Total amount distributed to all uplines
        "deposited": True,
        "approved": True,
    }

    cached_users: dict[str, UserInDB] = {}

    for (agent_phone, admin_phone) in distinct_agent_admin_pairs:
        # Filter players in the game that are under this specific agent AND this specific admin
        players_under_this_agent_admin_pair = get_players_under_agent_admin_pair(agent_phone, admin_phone, game_players_details, falsy_values)

        count_of_players_for_this_pair = len(players_under_this_agent_admin_pair)

        if count_of_players_for_this_pair == 0:
            # Should not happen if distinct_agent_admin_pairs is derived from game_players_details correctly
            continue

        # Calculate the portion of total_distributable relevant to this agent/admin pair's players
        proportion_of_players = count_of_players_for_this_pair / total_players_in_game
        distributable_for_this_specific_group = proportion_of_players * total_distributable_to_uplines

        agent_percent = 0
        admin_percent = 0

        async def get_user_with_cache(db, phone: str) -> Optional[UserInDB]:
            """Retrieves a user by phone, checking the cache first."""
            if phone in cached_users:
                return cached_users[phone]
            user = await get_user_by_phone(db.users, phone)
            if user:
                cached_users[phone] = user
            return user

        if not agent_phone == 'system':
            agent_obj: Optional[UserInDB] = await get_user_with_cache(db, agent_phone)
            if agent_obj:
                agent_percent = agent_obj.agentPercent
        
        if not admin_phone == 'system':
            admin_obj: Optional[UserInDB] = await get_user_with_cache(db, admin_phone)
            if admin_obj:
                admin_percent = admin_obj.adminPercent


        agent_commission_rate = agent_percent / 100.0
        admin_commission_rate_of_agent_share = admin_percent / 100.0
        
        system_commission_rate = 1 - agent_commission_rate # Remaining percentage for the system
        if(agent_commission_rate == 0):#if system dealt directly with the admin then the agent commission is 0(at least it must be)
            system_commission_rate = 1 - admin_commission_rate_of_agent_share

        # Agent's gross cut from the money generated by their group of players
        agent_gross_cut = distributable_for_this_specific_group * agent_commission_rate
        system_gross_cut = distributable_for_this_specific_group - agent_gross_cut
        # Admin's cut is a percentage of the agent's gross cut
        admin_actual_share = agent_gross_cut * admin_commission_rate_of_agent_share
        
        # Agent's net cut after the admin takes their share
        agent_net_share = agent_gross_cut - admin_actual_share

        # Create distribution record for the Admin
        if admin_actual_share > 0.009: # Check for a minimal amount to avoid tiny fractions
            admin_dist_record = WinningDistributionInDB(
                **common_game_data_for_record,
                yourPlayers=count_of_players_for_this_pair,
                yourPercent=admin_percent, # Admin's defined percentage
                amount=round(admin_actual_share, 2), # Round to 2 decimal places for currency
                phone=admin_phone,
                owner=agent_phone,
                role="admin",
                note=f"Admin commission from agent {agent_phone}."
            )
            distributions.append(admin_dist_record)

        # Create distribution record for the Agent
        if agent_net_share > 0.009: # Check for a minimal amount
            agent_dist_record = WinningDistributionInDB(
                **common_game_data_for_record,
                yourPlayers=count_of_players_for_this_pair,
                yourPercent=agent_percent, # Agent's defined percentage
                amount=round(agent_net_share, 2), # Round to 2 decimal places
                phone=agent_phone,
                owner="system",
                role="agent",
                note=f"Agent commission (net) - (admin {admin_phone} took {admin_percent}%)."
            )
            distributions.append(agent_dist_record)

        # Create distribution record for the Agent
        if system_gross_cut > 0.009: # Check for a minimal amount
            system_dist_record = WinningDistributionInDB(
                **common_game_data_for_record,
                yourPlayers=count_of_players_for_this_pair,
                yourPercent=system_commission_rate * 100, # Agent's defined percentage
                amount=round(system_gross_cut, 2), # Round to 2 decimal places
                phone="system",
                owner="system",
                role="system",
                note=f"system commission (net) - (agent {agent_phone} took {agent_percent}%)."
            )
            distributions.append(system_dist_record)
        
        
    return distributions

def get_players_under_agent_admin_pair(agent_phone, admin_phone, game_players_details, falsy_values):
    """
    Returns a list of players matching the given agent/admin pair.
    'system' is used to represent missing (falsy) agentId or adminId.
    """
    if agent_phone == 'system' and admin_phone == 'system':
        return [
            p_detail 
            for p_detail in game_players_details
            if p_detail.agentId in falsy_values and p_detail.adminId in falsy_values
        ]
    elif agent_phone == 'system':
        return [
            p_detail 
            for p_detail in game_players_details
            if p_detail.agentId in falsy_values and p_detail.adminId == admin_phone
        ]
    elif admin_phone == 'system':
        return [
            p_detail 
            for p_detail in game_players_details
            if p_detail.agentId == agent_phone and p_detail.adminId in falsy_values
        ]
    else:
        return [
            p_detail
            for p_detail in game_players_details
            if p_detail.agentId == agent_phone and p_detail.adminId == admin_phone
        ]

async def auto_distribute_manual_game(db_client: AsyncIOMotorDatabase = Depends(get_client)):
    try:
        print("********************************************** starting automatic manual game distributions ******************************************")

        db_name = settings.MONGODB_NAME
        distribution_collection = db_client[db_name].WinningDistributions
        game_collection = db_client[db_name].gametransactions

        undistributed_games = await get_undistributed_games(game_collection)
        if not undistributed_games or len(undistributed_games) == 0:
            raise Exception("No undistributed games found.")
        
        async with await db_client.start_session() as session:
            for game in undistributed_games:
                if not (game.game_completed and not game.game_distributed):
                    print(f"Game {game.game_id} is not completed or already distributed.")
                    continue

                try:
                    async with session.start_transaction():
                        distributions = await distribute_winning(game, db_client[db_name])
                        if not distributions:
                            print(f"############### distributions not found for Game {game.game_id}")
                            continue

                        # Insert distributions
                        await distribution_collection.insert_many([d.model_dump() for d in distributions], session=session)
                        
                        # Update game status
                        await game_collection.update_one(
                            {"game_id": game.game_id},
                            {"$set": {"game_distributed": True}}, 
                            session=session
                        )
                        
                        # Update credits for THIS game only
                        await credit_update_for_distribution(distributions, db_client[db_name], session)
                        
                        # If we reach here, commit the transaction
                        await session.commit_transaction()
                        print(f"✅ Successfully processed game {game.game_id}")

                except Exception as error:  # Catch ALL exceptions, not just PyMongoError
                    print(f"##################### exception thrown for game_id -> {game.game_id} ########################")
                    print(error)
                    print(f"############################ end exception for game_id {game.game_id} ########################")
                    
                    try:
                        await session.abort_transaction()
                        print(f"🔄 Transaction aborted for game_id -> {game.game_id}")
                    except Exception as abort_err:
                        print(f"❌ Failed to abort transaction for game_id -> {game.game_id}: {abort_err}")
                    continue
        
    except Exception as e: 
        print(f"❌ Overall error in auto_distribute_manual_game: {e}")

async def credit_update_for_distribution(distributions: List[WinningDistributionInDB], db: AsyncIOMotorDatabase, session) -> bool:
    try:
        #raise Exception('invalid error - > rollback test')
        credit_collection = db.creditbalances
        history_collection = db.transactionhistories

        grouped = defaultdict(lambda: {"amount": 0.0})
        for d in distributions:
            try:
                amount = float(d.amount)
                grouped[(d.gameId, d.phone)]["amount"] += amount
            except (ValueError, TypeError):
                print(f"⚠️ Invalid amount for {d.phone} in game {d.gameId}: {d.amount}")
                continue

        transaction_docs = []

        print("▶ updating credits and transaction histories within same session")
        print(f'length of grouped: {len(grouped)}')  # Fixed: use len() not .length
        
        for (gameId, phone), data in grouped.items():
            print(f'Processing {phone} for game {gameId}')
            amount = float(data["amount"])

            existing = await credit_collection.find_one({"phone": phone}, session=session)
            previous_balance = existing["current_balance"] if existing else 0.0
            
            await credit_collection.update_one(
                {"phone": phone},
                {
                    "$set": {
                        "previous_balance": previous_balance,
                        "modified_at": datetime.now(),
                    },
                    "$inc": {"current_balance": amount},
                    "$setOnInsert": {
                        "created_at": datetime.now(),
                        "remark": f"game distributed - {gameId}",
                    },
                },
                upsert=True,
                session=session
            )
            
            trx = TransactionHistoryCreate(
                phone=phone,
                game_id=gameId,
                transaction_ref=f"{gameId}-{phone}-{datetime.now().timestamp()}",
                amount=amount,
                net_amount=amount,
                type="commission",
                message=f"commission for game {gameId}",
                isdebit=True,
                reference=f"{gameId}-{phone}-{datetime.now().timestamp()}",
                remark="Auto distributed game winnings",
            )
            transaction_docs.append(trx.model_dump())

        if transaction_docs:
            await history_collection.insert_many(transaction_docs, session=session)

        print("✅ credit and transaction history prepared successfully")
        return True

    except Exception as e:
        print(f"❌ Error in credit_update_for_distribution: {e}")
        raise  # Re-raise to trigger transaction rollback

async def periodic_auto_distribute(db_client, interval_seconds: int):
    """
    Periodically runs the auto_distribute_manual_game routine based on .env interval.
    """
    while True:
        try:
            print(f"[{datetime.now()}] ▶ Running scheduled distribution...")
            await auto_distribute_manual_game(db_client=db_client)
            print(f"[{datetime.now()}] ✅ Distribution completed. Sleeping {interval_seconds}s.")
        except Exception as e:
            print(f"❌ Error during auto distribution loop: {e}")
        await asyncio.sleep(interval_seconds)