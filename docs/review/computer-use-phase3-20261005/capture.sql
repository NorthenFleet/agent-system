BEGIN READ ONLY;
SELECT jsonb_pretty(jsonb_build_object(
 'captured_at', now(),
 'missions', (SELECT jsonb_agg(to_jsonb(m)) FROM (SELECT id,status,title,plan_version,last_error,created_at,updated_at FROM orchestration_missions WHERE title LIKE 'CU-P3-20261005%') m),
 'steps', (SELECT jsonb_agg(jsonb_build_object(
   'id',s.id,'plan_version',s.plan_version,'status',s.status,'attempt_count',s.attempt_count,
   'contract',contract.value || jsonb_build_object('id',s.id,'mission_id',s.mission_id,'plan_version',s.plan_version),
   'output',s.result_json::jsonb->'structured_output',
   'quality',s.result_json::jsonb->'execution_quality',
   'completion',s.result_json::jsonb->'completion_decision'
 )) FROM mission_steps s JOIN mission_plan_versions p ON p.mission_id=s.mission_id AND p.version=s.plan_version
 CROSS JOIN LATERAL jsonb_array_elements(p.raw_plan::jsonb->'steps') contract(value)
 WHERE (contract.value->>'order_index')::int=s.order_index AND s.mission_id IN (SELECT id FROM orchestration_missions WHERE title LIKE 'CU-P3-20261005%')),
 'events', (SELECT jsonb_agg(to_jsonb(e)) FROM (SELECT mission_id,event_type,from_status,to_status,detail,created_at FROM mission_events WHERE mission_id IN (SELECT id FROM orchestration_missions WHERE title LIKE 'CU-P3-20261005%') ORDER BY created_at) e)
));
ROLLBACK;
