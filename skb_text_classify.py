from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
import torch.nn.functional as F
import configparser

config = configparser.ConfigParser()
config.read('conf.ini')

TC_MODEL = config['TEXT_CLASSIFY']['model_name']

model = AutoModelForSequenceClassification.from_pretrained(TC_MODEL)
tokenizer = AutoTokenizer.from_pretrained(TC_MODEL)


def text_classification(keyword):
    text = keyword
    inputs = tokenizer(text, return_tensors="pt")
    outputs = model(**inputs)
    logits = outputs.logits
    probabilities = F.softmax(logits, dim=-1)
    predicted_label = torch.argmax(probabilities, dim=-1).item()
    print(probabilities)
    print(predicted_label)
    return predicted_label


