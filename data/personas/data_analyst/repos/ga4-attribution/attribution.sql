WITH sessions AS (
  SELECT
    user_pseudo_id,
    session_id,
    session_start_timestamp,
    traffic_source.source AS source,
    traffic_source.medium AS medium,
    traffic_source.campaign AS campaign,
    purchase_revenue
  FROM `project.dataset.ga4_sessions`
  WHERE session_start_timestamp IS NOT NULL
),
ordered_sessions AS (
  SELECT
    user_pseudo_id,
    session_id,
    session_start_timestamp,
    COALESCE(source, '(direct)') AS source,
    COALESCE(medium, '(none)') AS medium,
    COALESCE(campaign, '(not set)') AS campaign,
    purchase_revenue,
    ROW_NUMBER() OVER (
      PARTITION BY user_pseudo_id
      ORDER BY session_start_timestamp, session_id
    ) AS touchpoint_index,
    COUNT(*) OVER (PARTITION BY user_pseudo_id) AS touchpoint_count
  FROM sessions
),
paths AS (
  SELECT
    user_pseudo_id,
    ARRAY_AGG(STRUCT(
      touchpoint_index,
      session_id,
      source,
      medium,
      campaign,
      purchase_revenue
    ) ORDER BY touchpoint_index) AS touchpoints
  FROM ordered_sessions
  GROUP BY user_pseudo_id
),
attribution AS (
  SELECT
    user_pseudo_id,
    tp.session_id,
    tp.source,
    tp.medium,
    tp.campaign,
    tp.touchpoint_index,
    tp.purchase_revenue,
    CASE
      WHEN touchpoint_count = 1 THEN 1.0
      WHEN touchpoint_index = 1 THEN 0.4
      WHEN touchpoint_index = touchpoint_count THEN 0.4
      ELSE 0.2 / NULLIF(touchpoint_count - 2, 0)
    END AS credit_share
  FROM paths,
  UNNEST(touchpoints) AS tp
  JOIN ordered_sessions USING (user_pseudo_id, session_id)
)
SELECT
  user_pseudo_id,
  session_id,
  source,
  medium,
  campaign,
  touchpoint_index,
  purchase_revenue,
  credit_share,
  purchase_revenue * credit_share AS attributed_revenue
FROM attribution
ORDER BY user_pseudo_id, touchpoint_index;
