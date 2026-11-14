WITH cohort_signups AS (
    SELECT
        u.user_id,
        date_trunc('month', u.created_at)::date AS cohort_month,
        u.plan_name,
        u.created_at::date AS signup_date
    FROM users u
    WHERE u.created_at IS NOT NULL
),
activity_months AS (
    SELECT
        a.user_id,
        date_trunc('month', a.activity_date)::date AS activity_month
    FROM user_activity a
    WHERE a.activity_date IS NOT NULL
    GROUP BY 1, 2
),
cohort_activity AS (
    SELECT
        cs.cohort_month,
        cs.plan_name,
        cs.user_id,
        am.activity_month,
        (
            EXTRACT(YEAR FROM age(am.activity_month, cs.cohort_month)) * 12
            + EXTRACT(MONTH FROM age(am.activity_month, cs.cohort_month))
        )::int AS months_since_signup
    FROM cohort_signups cs
    JOIN activity_months am
      ON am.user_id = cs.user_id
     AND am.activity_month >= cs.cohort_month
),
cohort_sizes AS (
    SELECT
        cohort_month,
        plan_name,
        COUNT(DISTINCT user_id) AS cohort_size
    FROM cohort_signups
    GROUP BY 1, 2
),
retention AS (
    SELECT
        ca.cohort_month,
        ca.plan_name,
        ca.months_since_signup,
        COUNT(DISTINCT ca.user_id) AS retained_users
    FROM cohort_activity ca
    WHERE ca.months_since_signup BETWEEN 0 AND 12
    GROUP BY 1, 2, 3
),
onboarding_funnel AS (
    SELECT
        s.user_id,
        s.plan_name,
        s.cohort_month,
        MAX(CASE WHEN e.event_name = 'signup_completed' THEN 1 ELSE 0 END) AS completed_signup,
        MAX(CASE WHEN e.event_name = 'profile_created' THEN 1 ELSE 0 END) AS created_profile,
        MAX(CASE WHEN e.event_name = 'workspace_joined' THEN 1 ELSE 0 END) AS joined_workspace,
        MAX(CASE WHEN e.event_name = 'first_project_created' THEN 1 ELSE 0 END) AS created_first_project
    FROM cohort_signups s
    LEFT JOIN onboarding_events e
      ON e.user_id = s.user_id
     AND e.event_date >= s.signup_date
     AND e.event_date < s.signup_date + INTERVAL '30 days'
    GROUP BY 1, 2, 3
)
SELECT
    r.cohort_month,
    r.plan_name,
    r.months_since_signup,
    cs.cohort_size,
    r.retained_users,
    ROUND(r.retained_users::numeric / NULLIF(cs.cohort_size, 0), 4) AS retention_rate,
    COUNT(*) FILTER (WHERE f.completed_signup = 1) AS users_completed_signup,
    COUNT(*) FILTER (WHERE f.created_profile = 1) AS users_created_profile,
    COUNT(*) FILTER (WHERE f.joined_workspace = 1) AS users_joined_workspace,
    COUNT(*) FILTER (WHERE f.created_first_project = 1) AS users_created_first_project
FROM retention r
JOIN cohort_sizes cs
  ON cs.cohort_month = r.cohort_month
 AND cs.plan_name = r.plan_name
LEFT JOIN onboarding_funnel f
  ON f.cohort_month = r.cohort_month
 AND f.plan_name = r.plan_name
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1, 2, 3;
