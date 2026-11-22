# Option Omega custom connector for Power Platform

A Power Platform custom connector (Power Automate, Power Apps, Logic Apps) for
[Option Omega](https://optionomega.com). It exposes every tool of the Option Omega
MCP server (`https://mcp.optionomega.com/mcp`) as a regular connector action with
typed input fields, for example *List saved backtests*, *Run backtest*,
*Get trade log* or *List closed live trades*.

No LLM is involved: the connector calls the MCP tools directly, so no AI tokens are
consumed. You only need an Option Omega account with MCP access and a Power Platform
licence that allows custom connectors (Premium).

> This is a community project. It is not affiliated with or supported by Option Omega.

## What is in this repository

| File | Purpose |
|---|---|
| `connector/apiDefinition.swagger.json` | OpenAPI 2.0 (Swagger) definition. **Import this one.** |
| `connector/script.csx` | Custom code: turns each action into an MCP `tools/call` request and unwraps the response. Required. |
| `connector/apiProperties.json` | OAuth settings and custom-code mapping for the `pac` CLI. Contains a `<CLIENT_ID>` placeholder. |
| `connector/generate_swagger.py` | Python description of the tools; writes `apiDefinition.swagger.json` and `apiProperties.json`. |

## How it works

The MCP server has a single endpoint (`POST /mcp`, JSON-RPC 2.0). To get one action
per tool, the Swagger file declares a placeholder path `/tools/<tool_name>` per tool
(for example `/tools/list_backtests` with operationId `ListBacktests`).

`script.csx` intercepts every call and

1. converts the operationId to the tool name (`ListBacktests` → `list_backtests`),
2. sends `{"method":"tools/call","params":{"name":"<tool_name>","arguments":<request body>}}`
   to `https://mcp.optionomega.com/mcp`, forwarding the user's OAuth token,
3. initializes an MCP session and retries if the server asks for one (HTTP 400/404),
4. reads the JSON-RPC answer (plain JSON or server-sent events) and returns the tool
   result (`structuredContent`, or the first text block parsed as JSON) as the action output.

The extra action **Get MCP server tool list** (`ListTools`) calls `tools/list` instead and
returns the tool names plus the raw list, which is handy to detect when Option Omega adds
or changes tools.

Without the custom code the calls go straight to `/tools/...` and fail with 404, so
always deploy the definition **and** `script.csx` together.

## Authentication

There is **no API key**. Option Omega uses OAuth 2.0 (AuthKit) and lets every client
register itself (dynamic client registration). Each connector therefore needs its own
OAuth client, registered with that connector's redirect URL. The client ID in this
repository is a placeholder on purpose.

| Setting | Value |
|---|---|
| Identity provider | Generic OAuth 2 |
| Authorization URL | `https://authkit.optionomega.com/oauth2/authorize` |
| Token URL / Refresh URL | `https://authkit.optionomega.com/oauth2/token` |
| Scope | `openid profile email offline_access` |

## Setup in the maker portal

### 1. Create the connector

1. In Power Automate (or Power Apps) go to **Custom connectors → New custom connector →
   Import an OpenAPI file** and upload `connector/apiDefinition.swagger.json`.
2. **Security** tab: choose *OAuth 2.0*, identity provider *Generic OAuth 2*, and enter the
   URLs and scope from the table above. Fill *Client ID* and *Client secret* with any
   placeholder for now.
3. **Code** tab: enable code, paste the content of `connector/script.csx` and apply it to
   all actions.
4. Click **Create connector**. The **Security** tab now shows the connector's
   **Redirect URL** (`https://global.consent.azure-apim.net/redirect/...`). Copy it.

### 2. Register an OAuth client with Option Omega

Run this once, replacing `<REDIRECT-URL>` with the URL you copied:

```bash
curl -s -X POST https://authkit.optionomega.com/oauth2/register \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Power Platform Option Omega","redirect_uris":["<REDIRECT-URL>"],"grant_types":["authorization_code","refresh_token"],"response_types":["code"],"token_endpoint_auth_method":"client_secret_post"}'
```

The answer contains `client_id` and `client_secret`. Enter both on the **Security** tab,
update the connector and keep the secret somewhere safe. Never commit it.

### 3. Test

**Test** tab → **New connection**, sign in with your Option Omega account, then run
*Get usage limits* and *List saved backtests*.

## Setup with the `pac` CLI

Put your client ID into `connector/apiProperties.json` (replace `<CLIENT_ID>`), then:

```bash
pac connector create \
  --api-definition-file connector/apiDefinition.swagger.json \
  --api-properties-file connector/apiProperties.json \
  --script-file connector/script.csx
```

Add `--solution-unique-name <YourSolution>` to create it inside a solution. Enter the
client secret on the **Security** tab afterwards. For updates use `pac connector update`
with `--connector-id` and the same files.

## Typical flow

1. **Get saved backtest** to obtain a complete `parameters` object.
2. **Run backtest** with that object (adjust it with expressions such as `setProperty(...)`).
3. **Do until** `status` is not `queued`/`running`: *Delay* by `pollAfterMs`, then
   **Get backtest status**.
4. **Get backtest results** or **Get trade log**.

Trade logs, live trades and equity curves return rows as arrays; `tradeColumns` or
`pointColumns` names the columns.

## Regenerating the definition

When Option Omega adds or changes tools:

```bash
cd connector
python generate_swagger.py   # writes apiDefinition.swagger.json and apiProperties.json
```

- `generate_swagger.py` holds the tool list (`TOOLS`: operationId, summary, description,
  input and output schema) and the shared schema building blocks. Add or change a tool there.
- The path of each action is `/tools/<tool_name>`; `script.csx` derives the tool name from the
  operationId, so keep the operationId the PascalCase form of the MCP tool name.
- New tools also need their operationId in `scriptOperations` (done automatically) and
  must be redeployed together with `script.csx`.
- Running `generate_swagger.py` overwrites `apiProperties.json`; put your client ID back in
  afterwards if you use `pac`.

Requires Python 3, no extra packages.

## Limits and notes

- Option Omega allows 60 tool calls per minute per user and only a few run starts per
  minute. Throttle polling loops with `pollAfterMs`.
- Custom code in Power Platform has a short execution time limit. Fetch large trade logs
  in pages with a smaller `limit`.
- Dates are `yyyy-MM-dd`; a backtest range can end yesterday (US Eastern) at the latest.
- Write actions (*Replace saved backtest*, *Replace saved portfolio*) cannot be undone.

## License

[MIT](LICENSE)
