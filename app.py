from datetime import datetime,timezone
from google.cloud import firestore as gcf_firestore 
from flask import Flask, render_template, request, url_for, redirect, jsonify,session
from xgboost import XGBClassifier
import firebase_admin
from firebase_admin import credentials, firestore , storage , auth 
import json
import uuid
import requests
from risk_calculation import risk

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
model = XGBClassifier()
model._estimator_type = "classifier"
model.load_model("xgb_foodrisk_model.json") 
# app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
cred = credentials.Certificate("food-donation-bc43b-firebase-adminsdk-fbsvc-d3bbc78ab3.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'food-donation-bc43b.firebasestorage.app'
})
db = firestore.client() 

@app.route('/',methods=['GET'])
def home():
    return render_template('index.html')


@app.route('/donor_register', methods=['GET','POST'])  
def donor_register():
    if session.get('uid'):
        return redirect(url_for('donate'))
    elif request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        name = request.form['donor_name']
        location = request.form['donor_location']
        city = request.form['city']
        contact_name = request.form['contact_name']
        session['location'] = location
        session['phone'] = phone
        session['city'] = city
        try:
            user = auth.create_user(
                email=email,
                password=password
            )
            uid = user.uid
            session['uid'] = uid
            db.collection('Donors').add({
            'email' : email, 
            'phone' : phone,
            'name' : name,
            'location' : location,
            'contact_name' : contact_name,
            'city' : city
        })
            return redirect(url_for('donate'))
        except Exception as e:
            return f"An error occurred: {e}", 400
    return render_template('donor_register.html')

@app.route('/donor_login', methods=['GET','POST'])  
def donor_login():
    if session.get('uid'):
        return redirect(url_for('donate'))
    elif request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        API_KEY = "AIzaSyCBZO_CJPkxm-02FNw5uy96XILbHL9AJyo"

        try:
            # Call Firebase REST API for email/password sign-in
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
            payload = {
                "email": email,
                "password": password,
                "returnSecureToken": True
            }
            r = requests.post(url, json=payload)
            data = r.json()

            if "idToken" in data:
                # Verify token with Firebase Admin SDK
                decoded_token = auth.verify_id_token(data["idToken"])
                uid = decoded_token["uid"]

                #Store session
                session["uid"] = uid
                donor_ref = db.collection('Donors').where('email','==',email)
                docs = donor_ref.stream()
                donor = []
                print(donor)
                for doc in docs:
                    post = doc.to_dict()
                    donor.append(post)
                session['location'] = donor[0]['location']
                session['phone'] = donor[0]['phone']
                session['city'] = donor[0]['city']
                return redirect(url_for('donate'))
            else:
                return jsonify({"error": data}), 401

        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('donor_login.html')

@app.route('/donate', methods=['GET'])
def donate():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    else:
        return render_template('donate.html')

@app.route('/post', methods=['POST'])   #**THEN**: JS calls /post (saves to Firebase)
def post_food():
    data = request.form
    food_types = json.loads(data.get('food_types', '[]'))  # Parse array
    is_refrigerated = data.get('is_refrigerated', 'false') == 'true'
    temp = float(data.get('temperature', 25))
    # hrs = data.get('hours_already_spent', 0)
    ft_array=food_types
    prepared_str = data.get('prepared_at')
    prepared_at = datetime.fromisoformat(prepared_str)  # native datetime
    prepared_at = prepared_at.replace(tzinfo=timezone.utc)
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
    doc_ref = db.collection('food_posts').document(post_id)
    doc_ref.set({
        'post_id' : post_id, 
        'description': data['description'],
        'quantity': data['quantity'],
        'location': session['location'],
        'temperature': temp,
        'is_refrigerated': is_refrigerated,
        'food_types': food_types,
        'claimed': False,
        'prepared_at': prepared_at,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'image_url' : image_url,
        'phone' : session['phone'],
        'city' : session['city'],
        'email' : auth.get_user(session['uid']).email
    })
    
    snap = doc_ref.get()
    doc_data = snap.to_dict()
    ts = doc_data['timestamp']                       
    created_at = ts.replace(tzinfo=timezone.utc)
    delta = created_at - prepared_at
    hours = delta.total_seconds() / 3600.0

    pred=risk(temp, hours, ft_array)

    if pred==0:
        prediction_str="low"
    elif pred==1:
        prediction_str="medium"
    elif pred==2:
        prediction_str="high"
    elif pred==3:
        prediction_str="very high"
    doc_ref.update({
        'prediction': prediction_str,
        'hours_already_spent': hours,
        'prepared_at':prepared_at
    })

    return jsonify({
        'success': True,
        'prediction': prediction_str,
        'hours': hours,
    }) , 200

@app.route('/temp', methods=['GET'])
def get_temp():
    cords = requests.get("http://api.openweathermap.org/geo/1.0/direct?q=amroha&limit=5&appid=de5d8dce9f9e7fda3b2df501d0a84bc3")
    lat = cords.json()[0]['lat']
    lon = cords.json()[0]['lon']
    conditions = requests.get(f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid=de5d8dce9f9e7fda3b2df501d0a84bc3")
    temp = conditions.json()['main']['temp']-273.15
    return jsonify({'temp': temp})

@app.route('/ngo_register', methods=['GET','POST'])  # ADD HOME ROUTE
def ngo_register():
    if session.get('uid'):
        return redirect(url_for('food_posts'))
    elif request.method == 'POST':
        email = request.form['email']
        darpan_id = request.form['ngo_darpan_id']
        password = request.form['password']
        phone = request.form['phone']
        name = request.form['ngo_name']
        location = request.form['ngo_location']
        contact_name = request.form['contact_name']
        city = request.form['city']
        session['ngo_location'] = location
        session['phone'] = phone
        session['city'] = city
        session['darpan_id'] = darpan_id
        try:
            user = auth.create_user(
                email=email,
                password=password
            )
            uid = user.uid
            session['uid'] = uid
            db.collection('NGOs').add({
            'email' : email, 
            'phone' : phone,
            'darpan_id' : darpan_id,
            'name' : name,
            'location' : location,
            'contact_name' : contact_name,
            'city' : city
            })
            return redirect(url_for('food_posts'))
        except Exception as e:
            return f"An error occurred: {e}", 400
    return render_template('ngo_register.html')

@app.route('/ngo_login', methods=['GET','POST'])  # ADD HOME ROUTE
def ngo_login():
    if session.get('uid'):
        return redirect(url_for('food_posts'))
    elif request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        API_KEY = "AIzaSyCBZO_CJPkxm-02FNw5uy96XILbHL9AJyo"

        try:
            # Call Firebase REST API for email/password sign-in
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
            payload = {
                "email": email,
                "password": password,
                "returnSecureToken": True
            }
            r = requests.post(url, json=payload)
            data = r.json()

            if "idToken" in data:
                # Verify token with Firebase Admin SDK
                decoded_token = auth.verify_id_token(data["idToken"])
                uid = decoded_token["uid"]

                #Store session
                session["uid"] = uid
                ngo_ref = db.collection('NGOs').where('email','==',email)
                docs = ngo_ref.stream()
                ngo = []
                print(ngo)
                for doc in docs:
                    post = doc.to_dict()
                    ngo.append(post)
                session['ngo_location'] = ngo[0]['location']
                session['phone'] = ngo[0]['phone']
                session['city'] = ngo[0]['city']
                session['darpan_id'] = ngo[0]['darpan_id']
                return redirect(url_for('food_posts'))
            else:
                return jsonify({"error": data}), 401

        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('ngo_login.html')


@app.route('/food_posts', methods=['GET','POST'])
def food_posts():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    else:
        posts_ref = db.collection('food_posts')
        docs = posts_ref.stream()
        posts = []
        print(posts)
        for doc in docs:
            post = doc.to_dict()
            post['id'] = doc.id
            if post['city'].lower() == session['city'].lower():
                posts.append(post)
        if request.method == 'POST':
            post_id = request.form['post_id']
            return redirect(url_for('claim',post_id=post_id))
        return render_template('food_posts.html',posts=posts)

@app.route('/claim', methods=['GET','POST'])
def claim():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    else:
        if session.get('darpan_id') is None:
            return jsonify({'error': 'Darpan ID not found.'}), 403
        post_id = request.values.get('post_id')
        posts_ref = db.collection('food_posts').where('post_id','==',post_id)
        docs = posts_ref.stream()
        post_id = request.values.get('post_id')
        posts_ref = db.collection('food_posts')
        docs = posts_ref.stream()
        for doc in docs:
            db.collection('food_posts').document(post_id).update({
                'claimed': True
            })
            if doc.to_dict()['post_id'] == post_id:
                post = doc.to_dict()
                return jsonify({'phone':post['phone'],'Mail':post['email'],'location':post['location']}),200
    

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
