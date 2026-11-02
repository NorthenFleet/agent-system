BEGIN READ ONLY;
SELECT jsonb_pretty(jsonb_build_object(
  'captured_at', now(),
  'missions', (SELECT jsonb_agg(to_jsonb(m)) FROM (SELECT id,title,status,project_id,mission_type,plan_version,approval_status,last_error,created_at,updated_at FROM orchestration_missions WHERE title LIKE 'CU-20261005%' ORDER BY created_at) m),
  'plans', (SELECT jsonb_agg(to_jsonb(p)) FROM (SELECT mission_id,version,status,summary,rationale,raw_plan::jsonb->'plan_quality' AS quality FROM mission_plan_versions WHERE mission_id IN (SELECT id FROM orchestration_missions WHERE title LIKE 'CU-20261005%') ORDER BY mission_id,version) p),
  'steps', (SELECT jsonb_agg(to_jsonb(s)) FROM (SELECT id,mission_id,plan_version,order_index,title,status,attempt_count,work_run_id,result_json::jsonb->'structured_output' AS output,result_json::jsonb->'completion_decision' AS completion, result_json::jsonb->'execution_quality' AS quality FROM mission_steps WHERE mission_id IN (SELECT id FROM orchestration_missions WHERE title LIKE 'CU-20261005%') ORDER BY mission_id,plan_version,order_index) s),
  'events', (SELECT jsonb_agg(to_jsonb(e)) FROM (SELECT mission_id,run_sequence,event_type,from_status,to_status,detail,created_at FROM mission_events WHERE mission_id IN (SELECT id FROM orchestration_missions WHERE title LIKE 'CU-20261005%') ORDER BY mission_id,run_sequence) e)
));
ROLLBACK;
