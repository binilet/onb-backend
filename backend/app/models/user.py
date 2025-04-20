from datetime import datetime,timezone
from pydantic import  Field, model_validator, field_validator
from schemas.userSchema import UserSchema
from bson import ObjectId

class UserInDB(UserSchema):
    id: str = Field(alias="_id")
    @model_validator(mode='before')
    def convert_objectid(cls, values):
        if "_id" in values and isinstance(values["_id"], ObjectId):
            values["_id"] = str(values["_id"])
        return values
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        exclude = {"password"}  # Specify the fields to exclude



