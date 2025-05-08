from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorClient,AsyncIOMotorDatabase
from schemas.gameTransactionSchema import GameTransactionInDB
from schemas.winningDistributionSchema import WinningDistributionInDB
from typing import List,Optional
from services.game_service import get_undistributed_games
from services.user_service import get_users_by_phones,get_user_by_phone
from models.user import UserInDB
from pymongo.errors import PyMongoError
from core.config import settings
from core.db import get_db


async def calculate_winning_distribution(
    db_client: AsyncIOMotorClient, is_production: bool = False
) -> List[WinningDistributionInDB]:
    """
    Calculate and store winning distributions for undistributed games atomically.
    Returns the list of inserted distributions.
    """
    db_name = settings.MONGODB_NAME
    distribution_collection = db_client[db_name].WinningDistributions
    game_collection = db_client[db_name].gametransactions

    undistributed_games = await get_undistributed_games(game_collection)
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

    distinct_agent_admin_pairs = list({
    (
        'system' if not player.agentId and not player.adminId else player.agentId,
        'system' if not player.agentId and not player.adminId else player.adminId,
    )
    for player in game_players_details
    })

    print(f"distinct agent admin pairs count: {len(distinct_agent_admin_pairs)} for game {game.game_id}")
    #print(game_players_details)
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
        "deposited": False,
    }

    cached_users: dict[str, UserInDB] = {}

    for (agent_phone, admin_phone) in distinct_agent_admin_pairs:
        # Filter players in the game that are under this specific agent AND this specific admin
        players_under_this_agent_admin_pair = [
            p_detail
            for p_detail in game_players_details
            if p_detail.agentId == agent_phone and p_detail.adminId == admin_phone
        ]
        
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

        agent_obj: Optional[UserInDB] = await get_user_with_cache(db, agent_phone)
        if agent_obj:
            agent_percent = 0 if agent_phone == 'system' else agent_obj.agentPercent

        admin_obj: Optional[UserInDB] = await get_user_with_cache(db, admin_phone)
        if admin_obj:
            admin_percent = 0 if admin_phone == 'system' else admin_obj.adminPercent


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
                note=f"Admin commission from agent {agent_phone} for game {game.game_id}."
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
                note=f"Agent commission (net) for game {game.game_id} (admin {admin_phone} took {admin_percent}%)."
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
                note=f"system commission (net) for game {game.game_id} (agent {agent_phone} took {agent_percent}%)."
            )
            distributions.append(system_dist_record)
        
        
    return distributions



# async def distribute_winning(game:GameTransactionInDB,db: AsyncIOMotorDatabase = Depends(get_db)) -> List[WinningDistributionInDB]:
#     """
#     this method will perform the actual game winning distribution
#     """
#     if not game.players or len(game.players) == 0:
#         print(f"Game {game.game_id} has no players.")
#         return None
    
#     #get all player objects to get their agents
#     game_players:List[UserInDB] = await get_users_by_phones(db.users,game.players)
#     if not game_players:
#         return None
    
#     total_distributable:float = game.total_winning - game.player_winning
#     total_players:int = len(game.players)

#     #distinct_agents = list({_user['agentId'] for _user in game_players}) #{} this is a set operator so distinct

#     distinct_agents = list({(_user['agentId'], _user['adminId']) for _user in game_players})

    
#     for (_agent,_admin) in distinct_agents:
#         if _agent == "system" and _admin == "system":
#             continue
        
#         #get the agent
#         agent_obj = await get_user_by_phone(db.users,_agent)
#         if not agent_obj:
#             continue

#         #get the admin
#         admin_obj = await get_user_by_phone(db.users,_admin)
#         if not admin_obj:
#             continue

#         agent_admin_players = [player for player in game_players if player.agentId == _agent and player.adminId == _admin]
#         agent_admin_player_count = len(agent_admin_players)
        
#         if agent_admin_player_count == 0:
#             continue

#         agentPercent = agent_obj.agentPercent
#         adminPercent = admin_obj.adminPercent
#         system_percent = 100 - agent_obj.agentPercent #whoever the system dealt with
#         agent_cut = (agent_admin_player_count/total_players) * total_distributable * agentPercent/100
#         system_cut = (agent_admin_player_count/total_players) * total_distributable * system_percent/100
#         #now distribute the total agent cut to the admins of that agent

#         admin_cut = agent_cut * adminPercent/100
#         final_agent_cut = agent_cut - admin_cut
        
