# Coffee Review Themes for Cobalt Coffee Roasters

In mid-2020, I worked with **Cobalt Coffee Roasters** on a fixed engagement to make large volumes of marketplace feedback easier to understand and act on. Their team had thousands of written reviews coming in, but the feedback was too granular to review efficiently by hand. They needed a way to quickly see recurring themes, understand how those themes were changing over time, and keep a pulse on sentiment without spending hours on manual tagging.

I built a small Streamlit app in Python that processed **38k marketplace reviews** and grouped them into clear, reusable themes. Under the hood, I used **BERTopic** with **Hugging Face Transformers** and **pandas** to prepare the text, cluster similar reviews, and organize the results into a format the team could explore easily. The app also tracked sentiment for each theme on a weekly basis, which gave Cobalt Coffee Roasters a simple way to spot shifts in customer feedback as they happened.

A big focus of the project was making the output practical for day-to-day use. Rather than delivering a one-off analysis, I built an interface that let the team review the themes and monitor sentiment trends over time. That helped turn a large, messy stream of comments into something operationally useful for product and customer insights.

```python
import streamlit as st
import pandas as pd
from bertopic import BERTopic

df = pd.read_csv("reviews.csv")
model = BERTopic()
topics, probs = model.fit_transform(df["review_text"].tolist())

st.write(df.assign(topic=topics).groupby("topic").size())
```

The result was a set of **12 stable themes** that gave the business a consistent way to categorize feedback. Most importantly, the app replaced about **2 days a month of manual tagging**, freeing the team from repetitive work and giving them faster access to the patterns hidden in customer reviews. For a food and beverage brand like Cobalt Coffee Roasters, that meant less time sorting comments and more time responding to what customers were actually saying.
