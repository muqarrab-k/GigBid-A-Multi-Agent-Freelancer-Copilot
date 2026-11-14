# Price Elasticity Study for Marrow & Pine Grocers

In early 2025, I worked with **Marrow & Pine Grocers** on a fixed-scope engagement to answer a simple but important retail question: how much should prices move, and for which items, before promotion depth starts to hurt margin? The team had a portfolio of products with different behaviors, but the existing approach treated price response too broadly. They needed a way to make promo decisions at the SKU level without relying on guesswork.

I built a hierarchical model in Python to study how **80 SKUs** responded to price changes. The workflow brought together `pandas` for data prep, `statsmodels` for supporting analysis, and `PyMC` for the core estimation work. The goal was to estimate price sensitivity in a way that allowed related SKUs to share information while still preserving the differences that matter in practice. That made the output more stable than a one-off per-SKU fit, especially where the data was thinner.

A small part of the modeling setup looked like this:

```python
import pandas as pd
import pymc as pm
import statsmodels.api as sm

df = pd.read_csv("sku_prices.csv")
X = sm.add_constant(df[["price", "promo_depth"]])

with pm.Model() as model:
    beta_price = pm.Normal("beta_price", 0, 1)
    beta_promo = pm.Normal("beta_promo", 0, 1)
    sigma = pm.Exponential("sigma", 1)

    mu = beta_price * X["price"] + beta_promo * X["promo_depth"]
    y = pm.Normal("y", mu=mu, sigma=sigma, observed=df["sales"])
```

The practical result was a decision tool the team could use to set promo depth with more confidence. Instead of applying the same discount logic across the board, Marrow & Pine Grocers could now compare SKU-level response patterns and choose promotion levels based on modeled sensitivity. That changed the team’s day-to-day workflow: promo planning became a more structured review of item behavior, rather than a manual negotiation between sales, margin, and intuition.

Over the quarter after the model was used, the **80 test SKUs** delivered a **gross margin increase of 0.6 points**. More importantly, the team now has a repeatable way to reason about price response when planning future promotions.
