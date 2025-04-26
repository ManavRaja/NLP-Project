import modal

# Define container image
hf_image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "transformers", "gguf", "torch", "accelerate", "bitsandbytes", "pymongo[srv]"
)

# Create a Modal app
app = modal.App(name="HF-Transformers-Lib-Phi4-14B-4b")

# Set the volume to download and load LLM weights from
model_volume = modal.Volume.from_name(
    "huggingface-cache-phi4-14B-4b", create_if_missing=True
)
MODEL_DIR = "/hf-cache"  # Volume mount path


@app.function(
    gpu="A100-40GB",
    image=hf_image,
    volumes={MODEL_DIR: model_volume},
    timeout=5400,  # 60 minutes
    secrets=[modal.Secret.from_name("mongodb-secret")], # TODO: Set on Modal dashboard
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
    collection = db["ParaMAWPS"] # TODO: Change to your assigned dataset collection

    # Model loading/storage logic
    if not os.path.exists(f"{MODEL_DIR}/config.json"):
        model = AutoModelForCausalLM.from_pretrained("unsloth/phi-4-unsloth-bnb-4bit")
        tokenizer = AutoTokenizer.from_pretrained("unsloth/phi-4-unsloth-bnb-4bit")
        model.save_pretrained(MODEL_DIR)
        tokenizer.save_pretrained(MODEL_DIR)
        model_volume.commit()

    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, device_map="auto")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)

    pipe = pipeline(task="text-generation", model=model, tokenizer=tokenizer)

    print("Loaded model into memory")

    system_prompt = "Please provide a numeric answer to the math question and provide your explanation step by step. Structure your response in the following way:      Explanation: <insert your step by step explanation here>      Numeric Answer: <insert your answer here>"

    query_filter = {"phi": {"$exists": False}}
    results = collection.find(filter=query_filter).limit(100)
    counter = 0
    for question in results:
        chat = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": question["original_text"], # TODO: Each dataset has different attribute for question
            },
        ]

        prompt = tokenizer.apply_chat_template(
            chat, tokenize=False, add_generation_prompt=True
        )
        prompt = tokenizer.apply_chat_template(
            chat, tokenize=False, add_generation_prompt=True
        )

        response = pipe(prompt, do_sample=True, return_full_text=False)
        # print(response[0]["generated_text"])

        collection.update_one(
            {"original_text": question["original_text"]},
            {"$set": {"phi": response[0]["generated_text"]}},
        )

        counter += 1
        print(f"Finished inferenced on {counter} questions.")
