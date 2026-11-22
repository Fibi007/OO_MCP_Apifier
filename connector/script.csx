// Custom code for the "Option Omega" Power Platform custom connector.
//
// Each action (operationId, e.g. ListBacktests) is translated into an MCP
// tools/call request to https://mcp.optionomega.com/mcp (tool list_backtests),
// with the action's request body becoming the tool arguments. The response
// (JSON or server-sent events) is unwrapped so that the action returns the
// tool's result object directly. The ListTools action calls tools/list instead.

public class Script : ScriptBase
{
    private const string McpUrl = "https://mcp.optionomega.com/mcp";
    private const string ProtocolVersion = "2025-06-18";

    public override async Task<HttpResponseMessage> ExecuteAsync()
    {
        var operationId = GetOperationId();
        if (operationId == "ListTools")
        {
            return await ListToolsAsync().ConfigureAwait(false);
        }

        var toolName = ToSnakeCase(operationId);

        var arguments = new JObject();
        if (this.Context.Request.Content != null)
        {
            var body = await this.Context.Request.Content.ReadAsStringAsync().ConfigureAwait(false);
            if (!string.IsNullOrWhiteSpace(body))
            {
                arguments = JObject.Parse(body);
            }
        }

        var callPayload = new JObject
        {
            ["jsonrpc"] = "2.0",
            ["id"] = 1,
            ["method"] = "tools/call",
            ["params"] = new JObject { ["name"] = toolName, ["arguments"] = arguments },
        };

        // Try statelessly first; if the server requires a session, initialize
        // once and retry with the Mcp-Session-Id.
        var response = await PostAsync(callPayload, null).ConfigureAwait(false);
        if (NeedsSession(response.StatusCode))
        {
            var sessionId = await InitializeAsync().ConfigureAwait(false);
            response = await PostAsync(callPayload, sessionId).ConfigureAwait(false);
        }

        var responseText = response.Content == null
            ? string.Empty
            : await response.Content.ReadAsStringAsync().ConfigureAwait(false);

        if (!response.IsSuccessStatusCode)
        {
            return CreateJsonResponse(response.StatusCode, new JObject
            {
                ["error"] = "MCP server responded with HTTP " + (int)response.StatusCode,
                ["details"] = responseText,
            });
        }

        var message = ParseRpcMessage(responseText, response.Content.Headers.ContentType?.MediaType);
        if (message == null)
        {
            return CreateJsonResponse(HttpStatusCode.BadGateway, new JObject
            {
                ["error"] = "Could not read the response of the MCP server.",
                ["details"] = responseText,
            });
        }

        if (message["error"] != null)
        {
            return CreateJsonResponse(HttpStatusCode.BadRequest, new JObject
            {
                ["error"] = message["error"]["message"]?.ToString(),
                ["details"] = message["error"],
            });
        }

        var result = message["result"] as JObject ?? new JObject();
        var payload = ExtractToolResult(result);

        if (result.Value<bool?>("isError") == true)
        {
            return CreateJsonResponse(HttpStatusCode.BadRequest, new JObject
            {
                ["error"] = "The tool " + toolName + " reported an error.",
                ["details"] = payload,
            });
        }

        return CreateJsonResponse(HttpStatusCode.OK, payload);
    }

    // ListTools action: MCP method tools/list (all pages). Returns the tool list,
    // the tool names and the unchanged list as text (raw) for comparisons.
    private async Task<HttpResponseMessage> ListToolsAsync()
    {
        var tools = new JArray();
        string cursor = null;
        string sessionId = null;
        var sessionTried = false;

        do
        {
            var listParams = new JObject();
            if (cursor != null)
            {
                listParams["cursor"] = cursor;
            }
            var listPayload = new JObject
            {
                ["jsonrpc"] = "2.0",
                ["id"] = 1,
                ["method"] = "tools/list",
                ["params"] = listParams,
            };

            var response = await PostAsync(listPayload, sessionId).ConfigureAwait(false);
            if (NeedsSession(response.StatusCode) && !sessionTried)
            {
                sessionTried = true;
                sessionId = await InitializeAsync().ConfigureAwait(false);
                response = await PostAsync(listPayload, sessionId).ConfigureAwait(false);
            }

            var responseText = response.Content == null
                ? string.Empty
                : await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            if (!response.IsSuccessStatusCode)
            {
                return CreateJsonResponse(response.StatusCode, new JObject
                {
                    ["error"] = "MCP server responded with HTTP " + (int)response.StatusCode,
                    ["details"] = responseText,
                });
            }

            var message = ParseRpcMessage(responseText, response.Content.Headers.ContentType?.MediaType);
            if (message == null || message["error"] != null)
            {
                return CreateJsonResponse(HttpStatusCode.BadGateway, new JObject
                {
                    ["error"] = "tools/list failed.",
                    ["details"] = message?["error"] ?? (JToken)responseText,
                });
            }

            var result = message["result"] as JObject ?? new JObject();
            foreach (var tool in (result["tools"] as JArray) ?? new JArray())
            {
                tools.Add(tool);
            }
            cursor = result.Value<string>("nextCursor");
        }
        while (!string.IsNullOrEmpty(cursor));

        var toolNames = new JArray(tools.Select(t => t.Value<string>("name")).OrderBy(n => n));

        return CreateJsonResponse(HttpStatusCode.OK, new JObject
        {
            ["toolCount"] = tools.Count,
            ["toolNames"] = toolNames,
            ["tools"] = tools,
            ["raw"] = tools.ToString(Newtonsoft.Json.Formatting.None),
        });
    }

    private string GetOperationId()
    {
        var operationId = this.Context.OperationId;
        // Depending on the environment, the operationId arrives Base64-encoded.
        if (!Regex.IsMatch(operationId, "^[A-Za-z]+$"))
        {
            try
            {
                operationId = Encoding.UTF8.GetString(Convert.FromBase64String(operationId));
            }
            catch (FormatException)
            {
            }
        }
        return operationId;
    }

    private static string ToSnakeCase(string pascalCase)
    {
        return Regex.Replace(pascalCase, "(?<!^)([A-Z])", "_$1").ToLowerInvariant();
    }

    private static bool NeedsSession(HttpStatusCode statusCode)
    {
        return statusCode == HttpStatusCode.BadRequest || statusCode == HttpStatusCode.NotFound;
    }

    private async Task<HttpResponseMessage> PostAsync(JObject payload, string sessionId)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, McpUrl)
        {
            Content = CreateJsonContent(payload.ToString(Newtonsoft.Json.Formatting.None)),
        };
        request.Headers.Authorization = this.Context.Request.Headers.Authorization;
        request.Headers.Accept.ParseAdd("application/json");
        request.Headers.Accept.ParseAdd("text/event-stream");
        request.Headers.Add("MCP-Protocol-Version", ProtocolVersion);
        if (!string.IsNullOrEmpty(sessionId))
        {
            request.Headers.Add("Mcp-Session-Id", sessionId);
        }
        return await this.Context.SendAsync(request, this.CancellationToken).ConfigureAwait(false);
    }

    private async Task<string> InitializeAsync()
    {
        var initialize = new JObject
        {
            ["jsonrpc"] = "2.0",
            ["id"] = 0,
            ["method"] = "initialize",
            ["params"] = new JObject
            {
                ["protocolVersion"] = ProtocolVersion,
                ["capabilities"] = new JObject(),
                ["clientInfo"] = new JObject { ["name"] = "power-automate-optionomega", ["version"] = "1.0" },
            },
        };
        var response = await PostAsync(initialize, null).ConfigureAwait(false);

        string sessionId = null;
        IEnumerable<string> values;
        if (response.Headers.TryGetValues("Mcp-Session-Id", out values))
        {
            sessionId = values.FirstOrDefault();
        }

        var initialized = new JObject { ["jsonrpc"] = "2.0", ["method"] = "notifications/initialized" };
        await PostAsync(initialized, sessionId).ConfigureAwait(false);

        return sessionId;
    }

    // Reads the JSON-RPC response, also when the server sends it as server-sent events.
    private static JObject ParseRpcMessage(string text, string mediaType)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return null;
        }

        if (mediaType == "text/event-stream")
        {
            JObject last = null;
            foreach (var line in text.Split('\n'))
            {
                var trimmed = line.TrimEnd('\r');
                if (!trimmed.StartsWith("data:"))
                {
                    continue;
                }
                var data = trimmed.Substring(5).Trim();
                if (data.Length == 0)
                {
                    continue;
                }
                var candidate = JObject.Parse(data);
                if (candidate["result"] != null || candidate["error"] != null)
                {
                    last = candidate;
                }
            }
            return last;
        }

        return JObject.Parse(text);
    }

    // Prefers structuredContent; otherwise the first text block is parsed as JSON.
    private static JToken ExtractToolResult(JObject result)
    {
        if (result["structuredContent"] is JObject structured)
        {
            return structured;
        }

        var text = (result["content"] as JArray)?
            .FirstOrDefault(c => c.Value<string>("type") == "text")?
            .Value<string>("text");

        if (text == null)
        {
            return result;
        }

        try
        {
            return JToken.Parse(text);
        }
        catch (Newtonsoft.Json.JsonReaderException)
        {
            return new JObject { ["text"] = text };
        }
    }

    private static HttpResponseMessage CreateJsonResponse(HttpStatusCode statusCode, JToken body)
    {
        return new HttpResponseMessage(statusCode)
        {
            Content = CreateJsonContent(body.ToString(Newtonsoft.Json.Formatting.None)),
        };
    }
}
