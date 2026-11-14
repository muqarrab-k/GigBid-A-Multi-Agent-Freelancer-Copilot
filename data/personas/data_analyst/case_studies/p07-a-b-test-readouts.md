# A/B Test Readouts for Hearthstone Games

At **Hearthstone Games**, I worked on a recurring analytics need that was slowing down the team’s decision-making around in-app store changes. They needed a reliable way to review A/B tests, understand whether results were trustworthy before launch, and turn each readout into a consistent decision-making artifact that the team could use without rebuilding the analysis from scratch every time.

I was brought in on an hourly basis from **2022-08 to 2022-10** to create a repeatable readout process for these experiments. My focus was to make the workflow easier for the team to run, easier to interpret, and more consistent across tests. I built a readout template that combined SQL-based data extraction with Python analysis using `statsmodels`, and I added power checks before launch so the team could spot tests that were unlikely to produce useful answers.

A simple version of the analysis flow looked like this:

```python
from statsmodels.stats.power import TTestIndPower

analysis = TTestIndPower()
power = analysis.solve_power(
    effect_size=0.25,
    nobs1=5000,
    alpha=0.05,
    ratio=1.0,
    alternative="two-sided"
)
print(power)
```

The main deliverable was not just a one-off report, but a **repeatable readout template** the team could use again and again for in-app store experiments. That changed how Hearthstone Games worked internally: instead of treating each test as a custom analysis project, the team could follow a standard process for checking readiness, evaluating outcomes, and deciding whether to continue, stop, or act on results.

Over the engagement, I analysed **11 experiments**. In **2 cases**, the pre-launch checks showed the tests were underpowered, and those were stopped early rather than wasting more time and traffic on them. That helped the team avoid drawing conclusions from weak data and gave them a cleaner path to testing store changes with more confidence.

Overall, the project gave Hearthstone Games a more structured and repeatable way to handle A/B test readouts, with less manual rework and a clearer process for making decisions from each experiment.
