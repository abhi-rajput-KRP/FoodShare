<h1>FoodShare – Food Donation Platform</h1>
<h4>FoodShare is a web application that connects food donors with nearby NGOs to reduce food waste and hunger. Donors can post surplus food with details and photos, while NGOs can browse and claim safe, available food in their city. An integrated machine learning model estimates spoilage risk based on food type, temperature and time, helping ensure that only safe food is distributed.</h4>

<h3>🔗 Live Demo: </h3>
[Visit Application](https://foodshare-donation.onrender.com)

<h3>🛠 Status: TechSprint Hackathon / project prototype </h3>

<h2>FEATURES</h2>

* <h3>Donor dashboard</h3>

  * Upload a photo and description of surplus food

  * Select food categories (rice, curries, breads, sweets, etc.)

  * Auto‑fetch ambient temperature by city and mark if food is refrigerated

  * Enter or infer preparation time to estimate time already spent

* <h3>AI spoilage risk prediction</h3>

  * Uses a trained ML model (XGBoost) to estimate spoilage risk

  * Considers food type, temperature and time since preparation/posting

  * Stores prediction and hours in Firestore for each donation

* <h3>NGO / receiver view</h3>

  * List of available food posts with description, image, location and risk

  * Ability to claim a post so others cannot double‑book

  * Phone and city of donor to coordinate pickup

* <h3>Tech stack</h3>

  * Backend: Flask (Python)

  * ML: scikit‑learn / XGBoost (risk model)

  * Database: Firebase Firestore, Firebase Storage (images)

  * Frontend: HTML, CSS, Bootstrap 5, vanilla JS

  * Deployment: Render
<h3>PROJECT STRUCTURE</h3>

```
FoodShare/
├── .gitignore
├── README.md
├── app.py
├── food_dataset_preparation.ipynb
├── food_risk_dataset.csv
├── preview/
│   ├── app_creds.png
│   ├── app_creds1.png
│   ├── app_creds2.png
│   ├── app_creds3.png
│   └── image.png
├── requirements.txt
├── risk_calculation.py
├── templates/
│   ├── donate.html
│   ├── donor_login.html
│   ├── donor_register.html
│   ├── food_posts.html
│   ├── index.html
│   ├── ngo_login.html
│   ├── ngo_register.html
│   ├── donor_invalid.html
│   ├── ngo_invalid.html
│   ├── error.html
│   ├── claim.html
│   └── static/
│       ├── favicon.ico
│       └── style.css
├── training_model.py
└── xgb_foodrisk_model.json
```
<h3>SETUP</h3>

### 1. Create a Virtual Environment</h4>

#### 🪟 Windows (CMD or PowerShell)
```
python -m venv venv 
venv\Scripts\activate
```

#### 🍎 macOS / 🐧 Linux
```
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
`pip install -r requirements.txt`

<!-- ### 3. Configure APIs and SDKs in app.py

![app.py-cerds](preview/app_creds.png)<br><br>
![app.py-cerds](preview/app_creds1.png)<br><br>
![app.py-cerds](preview/app_creds2.png)<br><br>
![app.py-cerds](preview/app_creds3.png)<br><br> -->

### 3. Run the Application
`python app.py`

<h2>How the Risk Model Works </h2>

* <h3>Input features:</h3>

  * Food categories selected in the donor form

  * Temperature (ambient or refrigerator)

  * Time difference between prepared_at and created_at (Firestore server timestamp)

* <h3>Model outputs a numeric risk class (e.g. 0 = low, 1 = medium, 2 = high).</h3>

* <h3>The prediction and computed hours are stored in Firestore with each post and shown in the UI as a human‑readable label (e.g. “High risk”).</h3>


<h2>Future Improvements</h2>
* Real‑time notifications to NGOs when new safe food is posted

* Better food type mapping and risk categories

* Multi‑city support and map view for nearby posts

* Automated re‑evaluation of risk as time passes
