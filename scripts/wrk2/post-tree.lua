-- wrk2 Lua script — POST /api/v1/trees/level-order
--
-- Standard 7-node binary tree used across all benchmark runs.
-- The same payload is reused on every request; wrk2 keeps it in memory.
--
-- Usage (wrk2 will call init() once and request() per request):
--   wrk2 -t4 -c50 -d90s -R500 --latency --script post-tree.lua <url>

wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"
wrk.headers["Accept"]       = "application/json"
wrk.body = '{"value":1,"left":{"value":2,"left":{"value":4},"right":{"value":5}},"right":{"value":3,"right":{"value":6}}}'

-- Fail the run if the server starts returning non-2xx responses.
function response(status, headers, body)
    if status ~= 200 then
        io.stderr:write("Unexpected status: " .. status .. "\n")
    end
end
