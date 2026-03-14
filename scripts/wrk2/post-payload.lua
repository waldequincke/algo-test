-- wrk2 Lua script — POST /api/v1/trees/level-order
--
-- Payload is injected via the WRK_PAYLOAD environment variable so the same
-- script can be reused for every scenario (small tree, large tree, etc.)
-- without modification.
--
-- Usage:
--   WRK_PAYLOAD=$(cat test-data/heavy_tree.json) \
--   wrk2 -t4 -c50 -d90s -R500 --latency -s scripts/wrk2/post-payload.lua <url>

local payload = os.getenv("WRK_PAYLOAD")
if not payload or payload == "" then
    -- Fallback: 7-node tree so a forgotten env var produces a valid run
    -- rather than a silent empty-body 400.
    payload = '{"value":1,"left":{"value":2,"left":{"value":4},"right":{"value":5}},"right":{"value":3,"right":{"value":6}}}'
    io.stderr:write("[post-payload.lua] WRK_PAYLOAD not set — using built-in 7-node fallback\n")
end

wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"
wrk.headers["Accept"]       = "application/json"
wrk.body = payload

function response(status, headers, body)
    if status ~= 200 then
        io.stderr:write("Non-200 response: " .. status .. "\n")
    end
end
