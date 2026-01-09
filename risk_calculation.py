import pandas as pd,numpy as np
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

model = XGBClassifier()
model._estimator_type = "classifier"
model.load_model("xgb_foodrisk_model.json") 

def risk(temp,hrs,ft_array):
  a=[]
  for i in ft_array:
    food_type=i
    if temp>24:
      temperature=2
    elif temp<=0:
      temperature=0
    else:
      temperature=1
    hours_already_spent=hrs
    data = pd.DataFrame([{
        "food_type": food_type,
        "temperature": temperature,
        "hours_already_spent": hours_already_spent
    }])
    data.food_type=data['food_type'].map({"Cooked rice dish":0,"Non-veg curries":1,"Dairy-based curries":2,"Dal/lentils":3,"Gravy-based veg curries":4,"Fresh breads":5,"Dry vegetable dishes":6,"Fried items":7,"Sweets":8})
    data.hours_already_spent=StandardScaler().fit_transform(data[["hours_already_spent"]])
    risk=model.predict(data)
    a.append([food_type,temperature,hours_already_spent, int(risk[0])])
    risks=np.array([i[3] for i in a])
    max_risk=int(risks.max())
  return max_risk