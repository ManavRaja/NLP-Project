import modal

# Define container image
hf_image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "transformers", "gguf", "torch", "accelerate", "bitsandbytes", "pymongo[srv]"
)

# Create a Modal app
app = modal.App(name="HF-Transformers-Lib-Deepseek-R1-Distill-14B-4b")

# Set the volume to download and load LLM weights from
model_volume = modal.Volume.from_name(
    "huggingface-cache-deepseek-r1-distill-14B-4b", create_if_missing=True
)
MODEL_DIR = "/hf-cache"  # Volume mount path


@app.function(
    gpu="L40S",
    image=hf_image,
    volumes={MODEL_DIR: model_volume},
    timeout=7200,  # 120 minutes
    secrets=[modal.Secret.from_name("mongodb-secret")],  # TODO: Set on Modal dashboard
)
def inference():
    import os
    import urllib

    from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer
    from pymongo import MongoClient

    # MongoDB connection
    user, password = map(
        urllib.parse.quote_plus,
        (os.environ["MONGO_USER"], os.environ["MONGO_PASSWORD"]),
    )
    host = os.environ["MONGO_HOST"]
    uri = f"mongodb://{user}:{password}@{host}/"

    client = MongoClient(uri)
    db = client["NLP-Project"]
    collection = db["ParaMAWPS"]  # TODO: Change to your assigned dataset collection

    # Model loading/storage logic (unchanged)
    if not os.path.exists(f"{MODEL_DIR}/config.json"):
        model = AutoModelForCausalLM.from_pretrained(
            "unsloth/DeepSeek-R1-Distill-Qwen-14B-unsloth-bnb-4bit"
        )
        tokenizer = AutoTokenizer.from_pretrained(
            "unsloth/DeepSeek-R1-Distill-Qwen-14B-unsloth-bnb-4bit"
        )
        model.save_pretrained(MODEL_DIR)
        tokenizer.save_pretrained(MODEL_DIR)
        model_volume.commit()

    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, device_map="auto")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)

    pipe = pipeline(task="text-generation", model=model, tokenizer=tokenizer)

    print("Loaded model into memory")

    system_prompt = "You will be given a math question, a solution that another LLM worked out, and its actual correct answer. Using that, determine if the worked out solution is correct or incorrect. If the worked out solution is incorrect, think about why it is incorrect and classify the type of error that the other LLM made. Use the following error taxonomy, if you cannot classify an error into one of these categories, just say “Other Error”; Calculation Error: Error appears during the calculation process, Counting Error: Error occurs during the counting process, Formula Confusion Error: Error appears when applying formula in inappropriate scenario, Question Misinterpretation Error: Error appears because the question is misunderstood, such as ignoring specific constraints in the question, Missing Step Error: Error entails an incomplete generation of reasoning process, lacking a necessary step, Confusing Concept Error: Error occurs because two similar but actually different concepts are mistakenly confused, Nonsensical Output: Inconceivable, illogical, or question-irrelevant output. Structure your response in the following way:Correct or Incorrect: <Insert whether the worked out solution is correct or incorrect>Error Category: <Insert error category if worked out solution is wrong or say N/A>"

    query_filter = {"grader": {"$exists": False}}
    results = collection.find(filter=query_filter).limit(400)
    counter = 0
    for question in results:
        chat = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": f"""Question: {question["original_text"]}
                Answer: {question["ans"]}
                Worked Out Solution by LLM: {question["phi"]}""",
                # TODO: Change depending on which model's answer to evaluate as well as the specific attribute for question and attribute for answer
                # TODO: Also add worked out solution if it was included in the dataset as well other other relevant things if needed
            },
        ]

        prompt = tokenizer.apply_chat_template(
            chat, tokenize=False, add_generation_prompt=True
        )
        prompt = tokenizer.apply_chat_template(
            chat, tokenize=False, add_generation_prompt=True
        )

        response = pipe(prompt, do_sample=True, return_full_text=False)

        collection.update_one(
            {
                "original_text": question["original_text"]
            },  # TODO: Each dataset has different attribute for question
            {"$set": {"grader-phi": response[0]["generated_text"]}}, # Change attribute name per dataset
        )

        counter += 1
        print(f"Finished inference on {counter} questions.")
