# Product recommendations for Tidewater Outfitters

I worked with **Tidewater Outfitters**, an e-commerce team, from **2022-01 to 2022-04** on an hourly engagement to improve how shoppers discovered products across the site.

Their team already had a strong catalog and healthy traffic, but product discovery was doing too much heavy lifting through manual merchandising. The goal was to make the storefront feel more responsive to shopper behavior without adding extra day-to-day work for the team. They needed recommendation placements that could keep up with changing inventory and user activity, while remaining practical to run in production.

I built a recommendation pipeline in **Python** and **PyTorch**, using **implicit** feedback to train models on **1.2M interactions**. The system generated two core experiences: **similar items** and **you-may-also-like** carousels. To keep response times fast, I cached recommendation results in **Redis**, and I used **AWS SageMaker** to support the production ML workflow.

A simple part of the serving setup looked like this:

```python
import redis

cache = redis.Redis(host="redis-cache", port=6379, decode_responses=True)

def get_recs(user_id):
    key = f"recs:{user_id}"
    cached = cache.get(key)
    if cached:
        return cached
    return None
```

What changed for Tidewater Outfitters was not just the model, but the operating model around it. Their team could now rely on recommendation carousels that were precomputed and cached, instead of assembling product suggestions by hand. That meant less manual maintenance, more consistent placements, and a smoother experience for shoppers browsing from one product to the next.

We validated the system with a **4-week A/B test**, which showed a **14% increase in click-through rate**. For the client team, that meant they had a recommendation layer they could trust in production, with a clearer path from shopper activity to site behavior and less ongoing effort to keep the experience fresh.
