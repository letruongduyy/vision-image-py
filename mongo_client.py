import os
from pymongo import MongoClient
from dotenv import load_dotenv
import certifi

load_dotenv(override=True)


def get_mongo_collection(tablename):
    mongo_uri = os.environ["DB_URL"]
    client = MongoClient(mongo_uri, tls=True, tlsCAFile=certifi.where())
    print(mongo_uri)
    db = client["visionimage"]
    collection = db[tablename]
    return collection
