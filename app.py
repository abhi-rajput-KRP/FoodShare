from flask import Flask, render_template, request, url_for, redirect, jsonify
from xgboost import XGBClassifier
import numpy as np,pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore , storage
import json
import uuid
from risk_calculation import risk

app = Flask(__name__)

model = XGBClassifier()
model._estimator_type = "classifier"
model.load_model("xgb_foodrisk_model.json") 

cred = credentials.Certificate("food-donation-bc43b-firebase-adminsdk-fbsvc-d3bbc78ab3.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'food-donation-bc43b.firebasestorage.app'
})
db = firestore.client() 

@app.route('/',methods=['GET'])
def home():
    return render_template('index.html')

@app.route('/donor', methods=['GET'])  # ADD HOME ROUTE
def form():
    return render_template('form.html')

@app.route('/post', methods=['POST'])   #**THEN**: JS calls /post (saves to Firebase)
def post_food():
    data = request.form
    food_types = json.loads(data.get('food_types', '[]'))  # Parse array
    post_id = str(uuid.uuid4())
    if 'photo' in request.files:
        photo = request.files['photo']
        if photo.filename:
            bucket = storage.bucket()
            filename = f"food_images/{post_id}_{photo.filename}"
            blob = bucket.blob(filename)
            blob.upload_from_file(photo, content_type=photo.content_type)
            blob.make_public()  # For display
            image_url = blob.public_url
        else :
            image_url = None
    db.collection('food_posts').add({
        'post_id' : post_id, 
        'description': data['description'],
        'quantity': data['quantity'],
        'location': data['location'],
        'temperature': float(data['temperature']),
        'food_types': food_types,
        'claimed': False,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'image_url' : image_url
    })
    
    return jsonify({'success': True})

@app.route("/predict", methods=["POST","GET"])
def predict():
    data = request.json
    temp = data.get('temperature', 25)
    hrs = data.get('hours_already_spent', 0)
    ft_array=data.get('food_type_array',9)
    
    pred=risk(temp, hrs, ft_array)
    print(f"array:{ft_array},temperature: {temp},hours_already_spent: {hrs},prediction: {pred}")

    return jsonify({"array":ft_array,"temperature": temp,"hours_already_spent": hrs,"prediction": pred})

if __name__ == "__main__":
    app.run(debug=True) 