# Telecom churn prediction

In early 2021, I worked with a client in telecom (name withheld) on a churn prediction problem that needed to be useful to both data science and retention teams. The business goal was straightforward: identify which subscribers were at risk of leaving early enough for the retention team to act on it. The practical challenge was making the output reliable at monthly cadence and easy to interpret at the individual customer level.

I built a monthly churn scoring pipeline for 380k subscribers using Python, pandas, and XGBoost. The workflow started with feature preparation from customer behavior and account history, then moved into training and validation against a held-out quarter to reduce the risk of overfitting to short-term patterns. I used MLflow to track experiments, compare runs, and keep the training process reproducible as features and parameters changed.

A major requirement was that the retention team should not only receive a score, but also understand why each customer was flagged. To support that, I added SHAP-based reason codes for every subscriber, so each monthly score came with a short list of the strongest drivers behind the prediction. That made the output much easier to use in day-to-day retention workflows, since the team could see which signals were pushing a customer into the high-risk segment.

A simplified version of the core training setup looked like this:

```python
import xgboost as xgb
from sklearn.model_selection import train_test_split

X_train, X_valid, y_train, y_valid = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

params = {
    "max_depth": 5,
    "learning_rate": 0.05,
    "n_estimators": 400,
    "objective": "binary:logistic",
    "eval_metric": "auc",
}

model = xgb.XGBClassifier(**params)
model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)
```

The final model reached an AUC of 0.84 on a held-out quarter and produced a top-decile lift of 3.1x. That meant the highest-risk group was substantially enriched for churn, which gave the retention team a much sharper target for outreach than a broad, untuned list.
