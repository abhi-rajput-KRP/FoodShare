from datetime import datetime,timezone
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
import math
from distance_calc import calculate_distance_km

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
    if session.get('darpan_id') is not None:
        return redirect(url_for('food_posts'))
    elif session.get('uid') is not None:
        return redirect(url_for('donor_dashboard'))
    return render_template('index.html')

@app.route('/donor_register', methods=['GET','POST'])  
def donor_register():
    if session.get('uid'):
        return redirect(url_for('donor_dashboard'))
    elif request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        name = request.form['donor_name']
        contact_name = request.form['contact_name']
        session['email']=email
        session['phone'] = phone
        donor_lat = request.form.get('donor_lat')
        donor_lng = request.form.get('donor_lng')
        donor_lat = float(donor_lat) if donor_lat else None
        donor_lng = float(donor_lng) if donor_lng else None
        session['lat'] = donor_lat
        session['lng'] = donor_lng

        url = "https://nominatim.openstreetmap.org/reverse"

        params = {
            "lat": donor_lat,
            "lon": donor_lng,
            "format": "json"
        }

        headers = {
            "User-Agent": "FoodShare/1.0"
        }

        # Fetch JSON from API
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()  # raises error if request failed

        data = response.json()  # Parse JSON into Python dict

        # Extract address
        location = data.get("display_name")
        session['location'] = location
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
            'donor_lat': donor_lat,
            'donor_lng': donor_lng
        })
            return redirect(url_for('donor_dashboard'))
        except Exception as e:
            return f"An error occurred: {e}", 400
    return render_template('donor_register.html')

@app.route('/donor_login', methods=['GET','POST'])  
def donor_login():
    if session.get('uid'):
        return redirect(url_for('donor_dashboard'))
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
                donor_ref = db.collection('Donors').where('email','==',email).limit(1)
                docs = list(donor_ref.stream())
                donor = docs[0].to_dict()
                session['location'] = donor['location']
                session['phone'] = donor['phone']
                session['email']=email
                session['lat'] = donor['donor_lat']
                session['lng'] = donor['donor_lng']
                return redirect(url_for('donor_dashboard'))
            else:
                return redirect(url_for('donor_invalid_login'))

        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('donor_login.html')

@app.route('/ngos_nearby',methods=['GET','POST'])
def ngos_nearby():
    if not session.get('uid'):
        return redirect(url_for('donor_login'))
    elif session.get('darpan_id') is not None:
        return redirect(url_for('food_posts'))
    email = session['email']
    donor_query = db.collection('Donors').where('email', '==', email).limit(1)
    donor_docs = list(donor_query.stream())

    if donor_docs:
        donor_data = donor_docs[0].to_dict()
    else:
        donor_data = {}
    donor_lat=donor_data.get('donor_lat')
    donor_lng=donor_data.get('donor_lng')

    lat_range = 30 / 111  # approx km per degree latitude
    lng_range = 30 / (111 * math.cos(math.radians(donor_lat)))

    min_lat = donor_lat - lat_range
    max_lat = donor_lat + lat_range
    min_lng = donor_lng - lng_range
    max_lng = donor_lng + lng_range

    ngo_query = (db.collection("NGOs").where("ngo_lat", ">=", min_lat).where("ngo_lat", "<=", max_lat))

    ngo_docs = ngo_query.stream()
    nearby_ngos = []

    for ngo in ngo_docs:
        ngo_data = ngo.to_dict()

        if not ngo_data.get("ngo_lng"):
            continue

        distance = calculate_distance_km(
            donor_lat, donor_lng,
            ngo_data["ngo_lat"], ngo_data["ngo_lng"]
        )

        if distance <= 30:
            ngo_data["distance"] = round(distance, 2)
            nearby_ngos.append(ngo_data)

    
    return render_template('ngos_nearby.html',donor=donor_data,ngos=nearby_ngos)

@app.route('/dashboard_donor',methods=['GET','POST'])
def donor_dashboard():
    if not session.get('uid'):
        return redirect(url_for('donor_login'))
    elif session.get('darpan_id') is not None:
        return redirect(url_for('food_posts'))
    email = session['email']
    donor_query = db.collection('Donors').where('email', '==', email).limit(1)
    donor_docs = list(donor_query.stream())

    if donor_docs:
        donor_data = donor_docs[0].to_dict()
    else:
        donor_data = {}
    posts=[]
    posts_ref = db.collection('food_posts').where('email', '==', email).where('claim_accepted','==',True)
    docs = posts_ref.stream()
    for doc in docs:
        data = doc.to_dict()
        posts.append(data)
    
    serves=0
    for i in posts:
        serves=serves+int(i['quantity'])
    points=serves*10
    
    stats = {
        "total_donations": len(posts),
        "points_earned": points,
        "people_fed": serves,
    }
    req_ref = db.collection('food_posts').where('email','==',email)
    docs = req_ref.stream()

    unclaimed_posts = []
    claim_requests = []

    for doc in docs:
        post = doc.to_dict()

        #  If donor already accepted → hide everywhere
        if post.get('donor_accepted') is True:
            continue
        # NO NGO has requested yet
        if not post.get('requested_by'):
            unclaimed_posts.append(post)

        # NGO has requested
        else:
            if not post.get('claim_accepted'):
                claim_requests.append(post)
    email= session.get('email')
    donor=[]
    posts_ref = db.collection('food_posts').where('email', '==', email)
    docs = posts_ref.stream()
    for doc in docs:
        data = doc.to_dict()
        donor.append(data)
    if request.method == 'POST':
        req_id = request.form.get('req_id')
        db.collection('food_posts').document(req_id).update({
            'claim_accepted': True
        })
    

        return redirect(url_for('donor_dashboard'))
    return render_template('donor_dashboard.html',donor=donor_data,stats=stats,reqs=claim_requests,unclaimed_posts=unclaimed_posts)



@app.route('/profile_donor')
def profile_donor():
    if not session.get('uid'):
        return redirect(url_for('donor_login'))
    elif session.get('darpan_id') is not None:
        return redirect(url_for('food_posts'))
    email = session['email']
    
    # Fetch donor data from Firestore
    donor_query = db.collection('Donors').where('email', '==', email).limit(1)
    donor_docs = list(donor_query.stream())
    
    if donor_docs:
        donor_data = donor_docs[0].to_dict()
    else:
        donor_data = {}
    
    posts=[]
    posts_ref = db.collection('food_posts').where('email', '==', email).where('claim_accepted','==',True)
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

@app.route('/my_donations', methods=['GET','POST'])
def my_donations():
    if session.get('uid') is None:
        return redirect(url_for('donor_login'))
    elif session.get('darpan_id') is not None:
        return redirect(url_for('food_posts'))
    else:
        email = session['email']
        donor_query = db.collection('Donors').where('email', '==', email).limit(1)
        donor_docs = list(donor_query.stream())
        if donor_docs:
            donor_data = donor_docs[0].to_dict()

        posts_ref = db.collection('food_posts').where('email', '==', email).where('claim_accepted','==',True)
        docs = posts_ref.stream()
        donations = []
        for doc in docs:
            post = doc.to_dict()
            donations.append(post)
        pending_count = 0
        completed_count = 0
        for post in donations:
            if post.get('pickup_status') == 'completed':
                completed_count += 1
            else:
                pending_count += 1
        return render_template('my_donation.html',posts=donations,donor=donor_data,pending_count=pending_count,completed_count=completed_count)

@app.route('/donate', methods=['GET'])
def donate():
    if session.get('uid') is None:
        return redirect(url_for('donor_login'))
    elif session.get('darpan_id') is not None:
        return redirect(url_for('food_posts'))
    else:
        return render_template('donate.html')
    
@app.route('/post', methods=['POST'])   #**THEN**: JS calls /post (saves to Firebase)
def post_food():
    if session.get('uid') is None:
        return redirect(url_for('donor_login'))
    elif session.get('darpan_id') is not None:
        return redirect(url_for('food_posts'))
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
        'claim_accepted': False,
        'prepared_at': prepared_at,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'image_url' : image_url,
        'phone' : session['phone'],
        'email' : auth.get_user(session['uid']).email,
        # NEW:
        'donor_lat': session.get('lat'),
        'donor_lng': session.get('lng'),
        'pickup_status': 'not_started'
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
    lat = session.get('lat')
    lon = session.get('lng')
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
        contact_name = request.form['contact_name']
        session['phone'] = phone
        session['darpan_id'] = darpan_id
        session['ngo_name'] = name
        session['email']=email
        ngo_lat = request.form.get('ngo_lat')
        ngo_lng = request.form.get('ngo_lng')

        ngo_lat = float(ngo_lat) if ngo_lat else None
        ngo_lng = float(ngo_lng) if ngo_lng else None
        url = "https://nominatim.openstreetmap.org/reverse"

        params = {
            "lat": ngo_lat,
            "lon": ngo_lng,
            "format": "json"
        }

        headers = {
            "User-Agent": "FoodDonation/1.0"
        }

        # Fetch JSON from API
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()  # raises error if request failed

        data = response.json()  # Parse JSON into Python dict

        # Extract address
        location = data.get("display_name")
        session['location'] = location
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
            'ngo_lat': ngo_lat,
            'ngo_lng': ngo_lng
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
                ngo_ref = db.collection('NGOs').where('email','==',email).limit(1)
                docs = list(ngo_ref.stream())
                ngo = docs[0].to_dict()
                session['location'] = ngo['location']
                session['phone'] = ngo['phone']
                session['darpan_id'] = ngo['darpan_id']
                session['ngo_name'] = ngo['name']
                session['email']=email
                session['ngo_lat'] = ngo.get('ngo_lat')
                session['ngo_lng'] = ngo.get('ngo_lng')
                return redirect(url_for('food_posts'))
            else:
                return redirect(url_for('ngo_invalid_login'))

        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('ngo_login.html')

@app.route('/food_posts', methods=['GET','POST'])
def food_posts():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    elif session.get('darpan_id') is None:
        return render_template('error.html')
    else:
        email = session['email']
        ngo_query = db.collection('NGOs').where('email', '==', email).limit(1)
        ngo_docs = list(ngo_query.stream())
        if ngo_docs:
            ngo_data = ngo_docs[0].to_dict()

    
        ngo_lat=ngo_data.get('ngo_lat')
        ngo_lng=ngo_data.get('ngo_lng')

        lat_range = 30 / 111  # approx km per degree latitude
        lng_range = 30 / (111 * math.cos(math.radians(ngo_lat)))

        min_lat = ngo_lat - lat_range
        max_lat = ngo_lat + lat_range
        min_lng = ngo_lng - lng_range
        max_lng = ngo_lng + lng_range

        donor_query = (db.collection("Donors").where("donor_lat", ">=", min_lat).where("donor_lat", "<=", max_lat))
        # .where("donor_lng", ">=", min_lng).where("donor_lng", "<=", max_lng))
        donor_docs = donor_query.stream()
        nearby_donors_data = []

        for donor in donor_docs:
            donor_data = donor.to_dict()

            if not donor_data.get("donor_lng"):
                continue

            distance = calculate_distance_km(
                donor_data["donor_lat"], donor_data["donor_lng"],
                ngo_lat, ngo_lng
            )

            if distance <= 30:
                donor_data["distance"] = round(distance, 2)
                nearby_donors_data.append(donor_data) 
        
        posts_ref = db.collection('food_posts')
        docs = posts_ref.stream()
        posts = []
        for doc in docs:
            post = doc.to_dict() 
            post['id'] = doc.id
            if post['email'] in [donor['email'] for donor in nearby_donors_data]:
                if post.get('requested_by') is None:
                    posts.append(post)
        if request.method == 'POST':
            post_id = request.form['post_id']
            return redirect(url_for('claim',post_id=post_id))
        return render_template('food_posts.html',posts=posts,ngo=ngo_data)
    
@app.route('/ngo_claimed_posts')
def ngo_claimed_posts():
    if session.get('uid') is None or session.get('darpan_id') is None:
        return redirect(url_for('ngo_login'))

    email = session['email']
    ngo_query = db.collection('NGOs').where('email', '==', email).limit(1)
    ngo_docs = list(ngo_query.stream())
    if not ngo_docs:
        return "NGO not found", 404
    ngo_data = ngo_docs[0].to_dict()

    ngo_lat = ngo_data.get('ngo_lat')
    ngo_lng = ngo_data.get('ngo_lng')

    posts_ref = db.collection('food_posts').where('claim_accepted', '==', True)
    posts = []
    for doc in posts_ref.stream():
        post = doc.to_dict()
        if (post.get('donor_lat') is not None and post.get('donor_lng') is not None):
            post['ngo_lat'] = ngo_lat
            post['ngo_lng'] = ngo_lng
            posts.append(post)
    pending_count = 0
    completed_count = 0
    for post in posts:
        if post.get('pickup_status') == 'completed':
            completed_count += 1
        else:
            pending_count += 1

    return render_template('pickup2.html', posts=posts, ngo=ngo_data, pending_count=pending_count, completed_count=completed_count)



@app.route('/profile_ngo')
def profile_ngo():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    elif session.get('darpan_id') is None:
        return render_template('error.html')
    else:
        email = session['email']
        ngo_query = db.collection('NGOs').where('email', '==', email).limit(1)
        ngo_docs = list(ngo_query.stream())
        if ngo_docs:
            ngo_data = ngo_docs[0].to_dict()
        return render_template('profile_ngo.html', ngo=ngo_data)

@app.route('/claim', methods=['GET'])
def claim():
    if session.get('uid') is None:
        return redirect(url_for('ngo_login'))
    else:
        if session.get('darpan_id') is None:
            return render_template('error.html')
        post_id = request.values.get('post_id')
        posts_ref = db.collection('food_posts').where('post_id','==',post_id)
        docs = posts_ref.stream()
        for doc in docs:
            db.collection('food_posts').document(post_id).update({
                'requested_by': {'name':session['ngo_name'], 'phone': session['phone']}
            })
            post = doc.to_dict()
            return render_template('claim.html',post=post)


@app.route('/update_pickup_status/<post_id>', methods=['POST'])
def update_pickup_status(post_id):
    if session.get('darpan_id') is None:
        return jsonify({'error': 'Not NGO'}), 403

    new_status = request.form.get('status')
    if new_status not in ['not_started', 'started', 'completed']:
        return jsonify({'error': 'Invalid status'}), 400

    db.collection('food_posts').document(post_id).update({
        'pickup_status': new_status,
        'claimed_by':session['ngo_name']
    })
    return jsonify({'success': True})


@app.route('/pickup/<post_id>')
def pickup_page(post_id):
    return render_template('pickup2.html')


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
