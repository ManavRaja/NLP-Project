import pymongo
import os
from dotenv import load_dotenv


# Load data from .env file
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DATABASE_NAME = "NLP-Project"
COLLECTION_NAME = "AQUA-RAT"
NUM_TO_KEEP = 500


client = None
try:
    # 1. Connect to MongoDB
    print(f"Connecting to MongoDB at {MONGO_URI}...")
    client = pymongo.MongoClient(MONGO_URI)
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]
    print(
        f"Connected to database '{DATABASE_NAME}' and collection '{COLLECTION_NAME}'."
    )

    # 2. Check current document count
    current_count = collection.count_documents({})
    print(f"Current document count: {current_count}")

    if current_count <= NUM_TO_KEEP:
        print(
            f"Collection already has {current_count} documents or fewer. No deletion needed."
        )
    else:
        print(f"Selecting {NUM_TO_KEEP} random document IDs to keep...")

        # 3. Use aggregation pipeline with $sample to get random IDs to keep
        #    $sample randomly selects the specified number of documents
        #    $project only keeps the _id field to minimize data transfer
        pipeline = [{"$sample": {"size": NUM_TO_KEEP}}, {"$project": {"_id": 1}}]

        ids_to_keep_cursor = collection.aggregate(pipeline)
        ids_to_keep = [doc["_id"] for doc in ids_to_keep_cursor]

        if len(ids_to_keep) < NUM_TO_KEEP:
            # This might happen if the collection size decreased between the count and aggregate
            # or if $sample had issues, though unlikely for simple sampling.
            print(
                f"Warning: Could only sample {len(ids_to_keep)} documents. Proceeding with this list."
            )
            if len(ids_to_keep) == 0 and current_count > 0:
                raise Exception(
                    "Failed to sample any documents to keep, but collection is not empty. Aborting."
                )

        print(f"Successfully selected {len(ids_to_keep)} document IDs to keep.")

        # 4. Delete documents whose _id is NOT IN the list of IDs to keep
        print("Deleting other documents...")

        # Use $nin (not in) operator
        delete_query = {"_id": {"$nin": ids_to_keep}}

        delete_result = collection.delete_many(delete_query)

        print(f"Deletion complete. Deleted {delete_result.deleted_count} documents.")

        # 5. Verify
        final_count = collection.count_documents({})
        print(f"Final document count in collection: {final_count}")
        if final_count != len(ids_to_keep):
            print(
                f"Warning: Final count ({final_count}) does not exactly match the number of IDs kept ({len(ids_to_keep)}). This might indicate concurrent modifications or issues during deletion."
            )


except pymongo.errors.ConnectionFailure as e:
    print(f"Error: Could not connect to MongoDB. {e}")
except pymongo.errors.OperationFailure as e:
    print(f"Error: MongoDB operation failed. {e.details}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
finally:
    # 6. Close the connection
    if client:
        client.close()
        print("MongoDB connection closed.")
