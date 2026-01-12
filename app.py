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
import dotenv
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
model = XGBClassifier()
model._estimator_type = "classifier"
model.load_model("xgb_foodrisk_model.json") 
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
cred = credentials.Certificate(dotenv.get_key(".env", "FIREBASE_SDK"))
firebase_admin.initialize_app(cred, {
    'storageBucket': dotenv.get_key(".env", "STORAGE_BUCKET")
})
db = firestore.client() 

@app.route('/',methods=['GET'])
def home():
    return render_template('index.html')

@app.route('/dashboard_donor',methods=['GET','POST'])
def donor():
    if not session.get('uid'):
        return redirect(url_for('donor_login'))
    email = session['email']
    print("Email in session:", email)
    donor_query = db.collection('Donors').where('email', '==', email).limit(1)
    donor_docs = list(donor_query.stream())

    if donor_docs:
        donor_data = donor_docs[0].to_dict()
        print("Donor data:", donor_data)
    else:
        donor_data = {}
        print("No donor found for email:", email)
    posts=[]
    posts_ref = db.collection('food_posts').where('email', '==', email)
    docs = posts_ref.stream()
    for doc in docs:
        data = doc.to_dict()
        posts.append(data)
    print(posts)
    if request.method == 'POST' and 'post_now_button' in request.form:
        return redirect(url_for('donate')) 
    
    serves=0
    for i in posts:
        serves=serves+int(i['quantity'])
    points=serves*10
    
    stats = {
        "feedback_received": 38,
        "points_earned": points,
        "people_fed": serves,
    }
    
    return render_template('donor_dashboard.html',donor=donor_data,posts=posts,stats=stats)

@app.route('/donor_register', methods=['GET','POST'])  
def donor_register():
    if session.get('uid'):
        return redirect(url_for('donor'))
    elif request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        name = request.form['donor_name']
        location = request.form['donor_location']
        city = request.form['city']
        contact_name = request.form['contact_name']
        session['email']=email
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
            return redirect(url_for('donor'))
        except Exception as e:
            return f"An error occurred: {e}", 400
    return render_template('donor_register.html')

@app.route('/donor_login', methods=['GET','POST'])  
def donor_login():
    if session.get('uid'):
        return redirect(url_for('donor'))
    elif request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        API_KEY = dotenv.get_key(".env", "FIREBASE_API_KEY")

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
                session['email']=email
                return redirect(url_for('donor'))
            else:
                return redirect(url_for('donor_invalid_login'))

        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('donor_login.html')

@app.route('/donate', methods=['GET'])
def donate():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    else:
        return render_template('donate.html')
    
@app.route('/profile_donor')
def profile_donor():
    if not session.get('uid'):
        return redirect(url_for('donor_login'))
    
    email = session['email']
    
    # Fetch donor data from Firestore
    donor_query = db.collection('Donors').where('email', '==', email).limit(1)
    donor_docs = list(donor_query.stream())
    
    if donor_docs:
        donor_data = donor_docs[0].to_dict()
    else:
        donor_data = {}
    
    posts=[]
    posts_ref = db.collection('food_posts').where('email', '==', email)
    docs = posts_ref.stream()
    for doc in docs:
        data = doc.to_dict()
        posts.append(data)
    
    serves=0
    for i in posts:
        serves=serves+int(i['quantity'])
    points=serves*10
    
    stats = {
        "people_fed":serves,
        "points":points,
    }
    return render_template('profile_donor.html', donor=donor_data, stats=stats,posts=posts)


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
    op_wheather_api_key = dotenv.get_key(".env", "OP_WEATHER_API_KEY")
    cords = requests.get(f"http://api.openweathermap.org/geo/1.0/direct?q=amroha&limit=5&appid={op_wheather_api_key}")
    lat = cords.json()[0]['lat']
    lon = cords.json()[0]['lon']
    conditions = requests.get(f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={op_wheather_api_key}")
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
        API_KEY = dotenv.get_key(".env", "FIREBASE_API_KEY")

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
                return redirect(url_for('ngo_invalid_login'))

        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('ngo_login.html')

@app.route('/my_donations', methods=['GET','POST'])
def my_donations():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    else:
        email = session['email']
        donor_query = db.collection('Donors').where('email', '==', email).limit(1)
        donor_docs = list(donor_query.stream())
        if donor_docs:
            donor_data = donor_docs[0].to_dict()

        posts_ref = db.collection('food_posts')
        docs = posts_ref.stream()
        donations = []
        for doc in docs:
            post = doc.to_dict()
            post['id'] = doc.id
            if post['email'] == session['email']:
                donations.append(post)
        if request.method == 'POST':
            post_id = request.form['post_id']
            return redirect(url_for('claim',post_id=post_id))
        return render_template('my_donation.html',posts=donations,donor=donor_data)

@app.route('/food_posts', methods=['GET','POST'])
def food_posts():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    else:
        email = session['email']
        donor_query = db.collection('Donors').where('email', '==', email).limit(1)
        donor_docs = list(donor_query.stream())

        if donor_docs:
            donor_data = donor_docs[0].to_dict()
        print("Donor data:", donor_data)
        posts_ref = db.collection('food_posts')
        docs = posts_ref.stream()
        posts = []
        print(posts)
        for doc in docs:
            post = doc.to_dict()
            post['id'] = doc.id
            if post['city'].lower() == session['city'].lower() and post['claimed'] == False:
                posts.append(post)
        if request.method == 'POST':
            post_id = request.form['post_id']
            return redirect(url_for('claim',post_id=post_id))
        return render_template('food_posts.html',posts=posts,donor=donor_data)

@app.route('/claim', methods=['GET','POST'])
def claim():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    else:
        if session.get('darpan_id') is None:
            return render_template('error.html')
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
                return render_template('claim.html',post=post)
    

@app.route('/ngo_invalid_login')
def ngo_invalid_login():
    return render_template('ngo_invalid.html')

@app.route('/donor_invalid_login')
def donor_invalid_login():
    return render_template('donor_invalid.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
