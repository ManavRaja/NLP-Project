# This file is for parsing the errors classified by the Grader LLM
from pymongo import  MongoClient
import os
import urllib
import re
os.environ["MODAL_TOKEN"] = "as-LtOqZZIFOI2ye6pRL3pkut" # TODO: Change to your token
user = "luke" # TODO: Change to your use
password = "yic;fddv$^&" # Super Secure TODO: change to your pass
host = "vps.manavrv.dev"
# NOTE: You can do a more secure login than this, but I was a little lazy here and just got it to work
uri = f"mongodb://{user}:{password}@{host}/?authSource=NLP-Project"
client = MongoClient(uri)
db = client["NLP-Project"]
collection = db["GSM8K"]  # TODO: Change to your assigned dataset collection
results = collection.find().limit(500)
grades = ["grader-phi", "grader-qwq"]
for grade in grades:
  count = 0
  errors = {'Calculation Error' : 0,
         'Counting Error' : 0,
         'Formula Confusion Error' : 0,
         'Question Misinterpretation Error' : 0,
         'Missing Step Error' : 0,
         'Confusing Concept Error' : 0,
         'Nonsensical Output': 0}
  for result in results:
    response = result[grade]
    match = re.search(r'Error Category.?: ', response)
    if match: # There is an error
      end = match.end()
      response_trunc = response[end - 1:]
      for error in errors:
        if re.search(error, response_trunc):
          errors[error] += 1
  # Pretty Print results
  print(f"{grade} Error summary:")
  total_errors = 0
  for error in errors:
    total_errors += errors[error]
    print(f"{error}: total errors: {errors[error]}, percent of total responses: {errors[error] / 5}%")
  print(f"Summary:")
  print(f"Total errors: {total_errors}, Accuracy: {(500 - total_errors) / 5}%")
  print()
