"""Writes apiDefinition.swagger.json and apiProperties.json for the "Option Omega" custom connector.

Each action corresponds to one tool of the MCP server https://mcp.optionomega.com/mcp.
The path /tools/<tool_name> is only a placeholder: script.csx rewrites every call
into a JSON-RPC request (tools/call) to /mcp and unwraps the response.

Usage:  python generate_swagger.py
"""

import json
from pathlib import Path

OUT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def s(description, type_="string", **extra):
    return {"type": type_, "description": description, **extra}


def obj(properties, required=None, description=None):
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    if description:
        schema["description"] = description
    return schema


def arr(items, description=None):
    schema = {"type": "array", "items": items}
    if description:
        schema["description"] = description
    return schema


NUM = {"type": "number"}
INT = {"type": "integer"}
STR = {"type": "string"}

RUN_ID = s("Run id, as returned by RunBacktest or RunPortfolio.")
SAVED_BACKTEST_ID = s("Saved backtest id (from ListBacktests).")
SAVED_PORTFOLIO_ID = s("Saved portfolio id (from ListPortfolios).")
OPTIMIZATION_ID = s("Optimization id (from RunOptimizer or ListOptimizations).")
LIMIT = s("Maximum number of entries per page.", "integer")
OFFSET = s("Zero-based start position; pass nextOffset from the previous response.", "integer")
INCLUDE_ARCHIVED = s("Include archived entries.", "boolean", default=False)
NOTE = s("Server note about this response.")
LINKED_BACKTEST_ID = s("savedBacktestId of the backtest the strategy was created from; null if created from "
                       "scratch. Not updated by later changes.")
ACCOUNT_NAME = s("Name of the brokerage account; null if the account was removed.")
IS_ACTIVE = s("Strategy is running: opens new trades and manages open ones.", "boolean")
PAUSE_NEW_TRADES = s("New trades paused; open trades are still managed.", "boolean")
INCLUDE_EXIT_RULES = s("Include exit rules per trade as columns legGroup and exitExecution (makes rows much "
                       "larger).", "boolean", default=False)

RUN_STATUS = obj({
    "runId": s("Run id."),
    "status": s("queued, running, complete, failed or cancelled."),
    "pollAfterMs": s("Milliseconds until the next status call; absent in a final state.", "integer"),
    "note": NOTE,
})

OPT_STATUS = obj({
    "optimizationId": s("Optimization id."),
    "status": s("queued, running, complete, failed or cancelled."),
    "progressPercent": s("Progress as a percentage.", "number"),
    "currentPeriod": s("Period currently being simulated."),
    "error": s("Failure reason when status is failed."),
    "totalIterations": s("Number of cells in the grid.", "integer"),
    "pollAfterMs": s("Milliseconds until the next status call; absent in a final state.", "integer"),
    "note": NOTE,
})

SAVED_BACKTEST_REF = obj({"savedBacktestId": s("Saved backtest id."), "note": NOTE})
SAVED_PORTFOLIO_REF = obj({"savedPortfolioId": s("Saved portfolio id."), "note": NOTE})

ANNUAL_METRICS = arr(obj({
    "year": INT,
    "profitLoss": NUM,
    "profitLossPercentage": NUM,
    "maxDrawdownPercentage": NUM,
}), "Metrics per calendar year.")

METRICS = {
    "startingFunds": NUM,
    "endingFunds": NUM,
    "profit": NUM,
    "minFunds": NUM,
    "maxFunds": NUM,
    "cagr": s("CAGR as a percentage.", "number"),
    "maxDrawdownPercentage": s("Max drawdown, as a negative percentage.", "number"),
    "marRatio": NUM,
    "sharpeRatio": NUM,
    "sortinoRatio": NUM,
    "winPercentage": NUM,
    "numberOfTrades": INT,
    "numberOfOpenTrades": INT,
    "averageProfitPerLot": NUM,
    "averageGainPerLot": NUM,
    "averageLossPerLot": NUM,
    "maxGainPerLot": NUM,
    "maxLossPerLot": NUM,
    "averageDaysInTrade": NUM,
    "averageMinutesInTrade": NUM,
    "totalPremium": NUM,
    "premiumCaptureRatePercentage": NUM,
    "annualMetrics": ANNUAL_METRICS,
}

STRATEGY_RESULTS = arr(obj({
    "savedBacktestId": STR,
    "name": STR,
    "numberOfTrades": INT,
    "profit": NUM,
    "winPercentage": NUM,
    "profitSharePercentage": NUM,
}), "Contribution per strategy.")

PORTFOLIO_METRICS = {**METRICS, "strategyResults": STRATEGY_RESULTS}

PAGE = {
    "totalCount": INT,
    "offset": INT,
    "nextOffset": s("Offset of the next page; null on the last page.", "integer"),
    "note": NOTE,
}

LABEL_FIELDS = {
    "name": s("New name. Omit to keep the current one."),
    "description": s("New description. Empty text clears it."),
    "tags": arr(STR, "Complete new list of tags."),
    "isShared": s("Share with other OptionOmega users.", "boolean"),
    "isArchived": s("Archive or restore.", "boolean"),
}

SAVE_FIELDS = {
    "runId": RUN_ID,
    "name": s("Name as it appears in the list."),
    "description": s("Optional description."),
    "tags": arr(STR, "Optional tags."),
    "isShared": s("Share. Defaults to false.", "boolean", default=False),
}

DIMENSION = obj({
    "parameterPath": s("Path exactly as returned by ListOptimizerParameters."),
    "start": s("First value (time: minutes since midnight).", "number"),
    "step": s("Step size; omit for sequence.", "number"),
    "end": s("Last value, inclusive.", "number"),
})

OPT_DIMENSION_OUT = obj({
    "parameterPath": STR,
    "label": STR,
    "valueType": s("number, time or sequence."),
    "start": NUM,
    "step": NUM,
    "end": NUM,
    "values": arr(NUM),
})


# ---------------------------------------------------------------------------
# Tools: (operationId, summary, description, request schema, response schema)
# The tool names follow from the operationId (PascalCase -> snake_case).
# ---------------------------------------------------------------------------

TOOLS = [
    # --- Backtest ---------------------------------------------------------
    ("RunBacktest", "Run backtest",
     "Starts a backtest and returns immediately with a runId. Then poll GetBacktestStatus. "
     "parameters is the complete strategy; the easiest way is to take the parameters object from"
     " GetSavedBacktest and change only what you need.",
     obj({"parameters": {
         "type": "object",
         "description": "Complete strategy configuration (JSON); see parameters in GetSavedBacktest.",
         "x-ms-summary": "Strategy (JSON)",
     }}, ["parameters"]),
     RUN_STATUS),
    ("GetBacktestStatus", "Get backtest status",
     "Status of a run started with RunBacktest. Polling interval: pollAfterMs.",
     obj({"runId": RUN_ID}, ["runId"]), RUN_STATUS),
    ("GetBacktestResults", "Get backtest results",
     "Metrics of a completed backtest run.",
     obj({"runId": RUN_ID}, ["runId"]), obj({**METRICS, "note": NOTE})),
    ("CancelBacktest", "Cancel backtest",
     "Stops a running or queued backtest run.",
     obj({"runId": RUN_ID}, ["runId"]), RUN_STATUS),
    ("ListBacktests", "List saved backtests",
     "Saved backtests, sorted by name, with headline metrics.",
     obj({"limit": LIMIT, "offset": OFFSET, "includeArchived": INCLUDE_ARCHIVED}),
     obj({"items": arr(obj({
         "id": STR, "name": STR, "description": STR, "tags": arr(STR),
         "isShared": {"type": "boolean"}, "isArchived": {"type": "boolean"},
         "underlying": STR, "rangeStart": STR, "rangeEnd": STR,
         "startingFunds": NUM, "endingFunds": NUM, "profit": NUM, "cagr": NUM,
         "maxDrawdownPercentage": NUM, "winPercentage": NUM, "numberOfTrades": INT,
         "marRatio": NUM, "sharpeRatio": NUM, "sortinoRatio": NUM,
         "premiumCaptureRatePercentage": NUM, "averageProfitPerLot": NUM,
     })), **PAGE})),
    ("GetSavedBacktest", "Get saved backtest",
     "Complete strategy (parameters) and metrics (result) of a saved backtest.",
     obj({"savedBacktestId": SAVED_BACKTEST_ID}, ["savedBacktestId"]),
     obj({
         "id": STR, "name": STR, "description": STR, "tags": arr(STR),
         "isShared": {"type": "boolean"}, "isArchived": {"type": "boolean"},
         "parameters": {"type": "object", "description": "Strategy configuration; usable as input for RunBacktest."},
         "result": obj(METRICS),
         "note": NOTE,
     })),
    ("SaveBacktest", "Save backtest run",
     "Saves a completed run as a new saved backtest.",
     obj(SAVE_FIELDS, ["runId", "name"]), SAVED_BACKTEST_REF),
    ("ReplaceSavedBacktest", "Replace saved backtest",
     "Overwrites the strategy and result of a saved backtest with a run. Cannot be undone.",
     obj({"runId": RUN_ID, "savedBacktestId": SAVED_BACKTEST_ID}, ["runId", "savedBacktestId"]),
     SAVED_BACKTEST_REF),
    ("EditSavedBacktest", "Rename or tag saved backtest",
     "Changes the name, description, tags, sharing or archived state. Only the fields you supply change.",
     obj({"savedBacktestId": SAVED_BACKTEST_ID, **LABEL_FIELDS}, ["savedBacktestId"]),
     SAVED_BACKTEST_REF),

    # --- Portfolio --------------------------------------------------------
    ("RunPortfolio", "Run portfolio",
     "Starts a portfolio backtest from saved backtests. Then poll GetPortfolioStatus.",
     obj({"parameters": obj({
         "strategies": arr(obj({
             "savedBacktestId": s("Id of a saved backtest."),
             "allocationPercentage": s("Allocation per trade as a percentage; omit to keep the saved value.", "number"),
             "maxAllocationAmount": s("Dollar cap per trade; 0 removes it.", "number"),
             "maxContractsPerTrade": s("Max contracts per trade; 0 removes the cap.", "integer"),
             "capitalPerContract": s("Capital per contract in USD; 0 turns it off.", "number"),
             "ignoreMarginRequirements": s("Ignore margin requirements.", "boolean"),
         }), "1 to 30 saved backtests."),
         "rangeStart": s("First day, yyyy-MM-dd."),
         "rangeEnd": s("Last day, yyyy-MM-dd; yesterday at the latest (US Eastern)."),
         "startingFunds": s("Starting funds in USD.", "number"),
         "closeOpenTradesAtTestCompletion": s("Close open trades at the end.", "boolean"),
         "monthlyWithdrawalMode": s("none, resetToStartingFunds or fixedAmount."),
         "monthlyWithdrawalAmount": s("Monthly withdrawal for fixedAmount.", "number"),
     }, ["strategies"])}, ["parameters"]),
     RUN_STATUS),
    ("GetPortfolioStatus", "Get portfolio status",
     "Status of a run started with RunPortfolio.",
     obj({"runId": RUN_ID}, ["runId"]), RUN_STATUS),
    ("GetPortfolioResults", "Get portfolio results",
     "Metrics of a completed portfolio run, including strategyResults.",
     obj({"runId": RUN_ID}, ["runId"]), obj({**PORTFOLIO_METRICS, "note": NOTE})),
    ("CancelPortfolio", "Cancel portfolio",
     "Stops a running or queued portfolio run.",
     obj({"runId": RUN_ID}, ["runId"]), RUN_STATUS),
    ("ListPortfolios", "List saved portfolios",
     "Saved portfolios, sorted by name, with headline metrics.",
     obj({"limit": LIMIT, "offset": OFFSET, "includeArchived": INCLUDE_ARCHIVED}),
     obj({"items": arr(obj({
         "id": STR, "name": STR, "description": STR, "tags": arr(STR),
         "isShared": {"type": "boolean"}, "isArchived": {"type": "boolean"},
         "rangeStart": STR, "rangeEnd": STR, "strategyCount": INT,
         "startingFunds": NUM, "endingFunds": NUM, "profit": NUM, "cagr": NUM,
         "maxDrawdownPercentage": NUM, "marRatio": NUM, "sharpeRatio": NUM, "sortinoRatio": NUM,
     })), **PAGE})),
    ("GetSavedPortfolio", "Get saved portfolio",
     "Settings, strategies and metrics of a saved portfolio.",
     obj({"savedPortfolioId": SAVED_PORTFOLIO_ID}, ["savedPortfolioId"]),
     obj({
         "id": STR, "name": STR, "description": STR, "tags": arr(STR),
         "isShared": {"type": "boolean"}, "isArchived": {"type": "boolean"},
         "settings": obj({
             "rangeStart": STR, "rangeEnd": STR, "startingFunds": NUM,
             "closeOpenTradesAtTestCompletion": {"type": "boolean"},
             "monthlyWithdrawalMode": STR, "monthlyWithdrawalAmount": NUM,
         }),
         "strategies": arr(obj({
             "savedBacktestId": STR, "name": STR, "underlying": STR,
             "allocationPercentage": NUM, "maxAllocationAmount": NUM,
             "maxContractsPerTrade": INT, "capitalPerContract": NUM,
             "ignoreMarginRequirements": {"type": "boolean"},
         })),
         "result": obj(PORTFOLIO_METRICS),
         "note": NOTE,
     })),
    ("SavePortfolio", "Save portfolio run",
     "Saves a completed portfolio run as a new saved portfolio.",
     obj(SAVE_FIELDS, ["runId", "name"]), SAVED_PORTFOLIO_REF),
    ("ReplaceSavedPortfolio", "Replace saved portfolio",
     "Overwrites a saved portfolio with a run. Cannot be undone.",
     obj({"runId": RUN_ID, "savedPortfolioId": SAVED_PORTFOLIO_ID}, ["runId", "savedPortfolioId"]),
     SAVED_PORTFOLIO_REF),
    ("EditSavedPortfolio", "Rename or tag saved portfolio",
     "Changes the name, description, tags, sharing or archived state. Only the fields you supply change.",
     obj({"savedPortfolioId": SAVED_PORTFOLIO_ID, **LABEL_FIELDS}, ["savedPortfolioId"]),
     SAVED_PORTFOLIO_REF),

    # --- Optimizer --------------------------------------------------------
    ("ListOptimizerParameters", "List optimizer parameters",
     "Parameters of a saved backtest that RunOptimizer can sweep, with their limits.",
     obj({"savedBacktestId": SAVED_BACKTEST_ID}, ["savedBacktestId"]),
     obj({
         "savedBacktestId": STR,
         "parameters": arr(obj({
             "parameterPath": STR, "label": STR, "category": STR, "valueType": STR,
             "unit": STR, "currentValue": NUM, "currentTime": STR, "precision": INT,
             "wholeNumbersOnly": {"type": "boolean"}, "allowedValues": arr(NUM),
         })),
         "limits": obj({
             "maxDimensions": INT, "maxStepsPerDimension": INT, "maxTotalIterations": INT,
             "minTimeMinutes": INT, "maxTimeMinutes": INT,
         }),
         "note": NOTE,
     })),
    ("RunOptimizer", "Run optimizer",
     "Starts a parameter sweep over a saved backtest. Then poll GetOptimizationStatus.",
     obj({
         "savedBacktestId": SAVED_BACKTEST_ID,
         "dimensions": arr(DIMENSION, "Parameters to sweep."),
         "rangeStart": s("First day, yyyy-MM-dd; omit to keep the saved value."),
         "rangeEnd": s("Last day, yyyy-MM-dd; omit to keep the saved value."),
         "startingFunds": s("Starting funds; omit to keep the saved value.", "number"),
     }, ["savedBacktestId", "dimensions"]),
     OPT_STATUS),
    ("GetOptimizationStatus", "Get optimization status",
     "Status and progress of an optimization.",
     obj({"optimizationId": OPTIMIZATION_ID}, ["optimizationId"]), OPT_STATUS),
    ("CancelOptimization", "Cancel optimization",
     "Stops a running or queued optimization.",
     obj({"optimizationId": OPTIMIZATION_ID}, ["optimizationId"]), OPT_STATUS),
    ("ListOptimizations", "List optimizations",
     "All optimizations of a saved backtest, newest first.",
     obj({"savedBacktestId": SAVED_BACKTEST_ID, "limit": LIMIT, "offset": OFFSET}, ["savedBacktestId"]),
     obj({"items": arr(obj({
         "id": STR, "name": STR, "status": STR, "progressPercent": NUM, "currentPeriod": STR,
         "error": STR, "createdAt": STR, "underlying": STR, "rangeStart": STR, "rangeEnd": STR,
         "startingFunds": NUM, "totalIterations": INT, "dimensions": arr(OPT_DIMENSION_OUT),
         "bestMetrics": obj({
             "profit": NUM, "profitPerTrade": NUM, "winPercentage": NUM,
             "premiumCaptureRatePercentage": NUM, "cagr": NUM, "maxDrawdownPercentage": NUM,
             "marRatio": NUM, "sharpeRatio": NUM, "sortinoRatio": NUM,
         }),
     })), **PAGE})),
    ("GetOptimizationResults", "Get optimization results",
     "Cells of a completed optimization; use sortBy to get the best cell first.",
     obj({
         "optimizationId": OPTIMIZATION_ID,
         "sortBy": s("Metric to sort by, e.g. cagr, marRatio, maxDrawdownPercentage."),
         "direction": s("desc (default, best first) or asc."),
         "limit": s("Cells per page, default 100, max 500.", "integer"),
         "offset": OFFSET,
     }, ["optimizationId"]),
     obj({
         "optimizationId": STR, "savedBacktestId": STR,
         "dimensions": arr(OPT_DIMENSION_OUT),
         "cells": arr(obj({
             "index": INT,
             "coordinate": arr(obj({"parameterPath": STR, "label": STR, "value": NUM, "time": STR})),
             "error": STR, "profit": NUM, "cagr": NUM, "sharpeRatio": NUM, "sortinoRatio": NUM,
             "marRatio": NUM, "maxDrawdownPercentage": NUM, "winPercentage": NUM,
             "premiumCaptureRatePercentage": NUM, "numberOfTrades": INT, "endingFunds": NUM,
             "averageProfitPerLot": NUM, "averageGainPerLot": NUM, "averageLossPerLot": NUM,
             "maxGainPerLot": NUM, "maxLossPerLot": NUM,
         })),
         "sortedBy": STR, "direction": STR, **PAGE,
     })),

    # --- Live trading (automated strategies) -------------------------------
    ("ListAutomatedStrategies", "List automated strategies",
     "Automated strategies that the trading platform runs live in the brokerage account, sorted "
     "by name. GetAutomatedStrategy returns the full settings.",
     obj({
         "limit": s("Maximum number of entries per page, default 100, max. 500.", "integer"),
         "offset": OFFSET,
         "includeArchived": INCLUDE_ARCHIVED,
     }),
     obj({"items": arr(obj({
         "id": s("Id for GetAutomatedStrategy."),
         "name": STR,
         "linkedBacktestId": LINKED_BACKTEST_ID,
         "underlying": STR,
         "allocationType": s("Percentage, FixedValue, FixedQuantity or CapitalPerContract."),
         "allocationAmount": s("Sizing value; meaning depends on allocationType.", "number"),
         "accountName": ACCOUNT_NAME,
         "tags": arr(STR),
         "isActive": IS_ACTIVE,
         "isArchived": {"type": "boolean"},
         "pauseNewTrades": PAUSE_NEW_TRADES,
     })), **PAGE})),
    ("GetAutomatedStrategy", "Get automated strategy",
     "One automated strategy with its current live settings. Times in US Eastern market time, "
     "prices and premiums in dollars per share.",
     obj({"strategyId": s("Id of the automated strategy (from ListAutomatedStrategies).")}, ["strategyId"]),
     obj({
         "id": STR, "name": STR,
         "description": s("Your own notes on the strategy."),
         "linkedBacktestId": LINKED_BACKTEST_ID,
         "underlying": STR,
         "accountName": ACCOUNT_NAME,
         "tags": arr(STR),
         "isActive": IS_ACTIVE,
         "isArchived": {"type": "boolean"},
         "pauseNewTrades": PAUSE_NEW_TRADES,
         "contractSelection": {"type": "object", "description": "Option structure (legs) and strike selection."},
         "allocation": {"type": "object", "description": "Position size and max. open trades."},
         "entry": {"type": "object", "description": "Entry conditions (times, frequency, filters)."},
         "legGroups": arr({"type": "object"}, "Leg groups with profit, loss and exit rules."),
         "execution": {"type": "object", "description": "Order execution for entry and exit."},
         "note": NOTE,
     })),
    ("ListOpenAutomatedTrades", "List open live trades",
     "Open trades of the automated strategies as shown on the app's live page. Values are "
     "approximations (updated about every minute during market hours, see lastUpdated). Rows are"
     " arrays; tradeColumns names the columns.",
     obj({
         "strategyIds": arr(STR, "Only trades of these strategies (ids from ListAutomatedStrategies)."),
         "sortBy": s("opened (default) or profit."),
         "direction": s("asc (default, oldest first) or desc."),
         "includeExitRules": INCLUDE_EXIT_RULES,
         "limit": s("Trades per page, default 1000, max 5000.", "integer"),
         "offset": OFFSET,
     }),
     obj({
         "tradeColumns": arr(STR, "Column names of the rows in trades."),
         "trades": arr({"type": "array", "items": {}}, "One row per trade."),
         "sortedBy": STR, "direction": STR, **PAGE,
     })),
    ("ListClosedAutomatedTrades", "List closed live trades",
     "Closed trades of the automated strategies by date of last close (US Eastern). Default: "
     "last 30 days, at most 90 days per call. Includes halted trades. Rows are arrays; "
     "tradeColumns names the columns.",
     obj({
         "closedFrom": s("First day, yyyy-MM-dd, inclusive; default 29 days before closedTo."),
         "closedTo": s("Last day, yyyy-MM-dd, inclusive; default today."),
         "strategyIds": arr(STR, "Only trades of these strategies (ids from ListAutomatedStrategies)."),
         "outcome": s("winners or losers; omit for all."),
         "reasonClosed": s("e.g. Profit Target or Stop Loss."),
         "sortBy": s("opened (default), closed or profit."),
         "direction": s("desc (default, newest first) or asc."),
         "includeExitRules": INCLUDE_EXIT_RULES,
         "limit": s("Trades per page, default 1000, max 5000.", "integer"),
         "offset": OFFSET,
     }),
     obj({
         "tradeColumns": arr(STR, "Column names of the rows in trades."),
         "trades": arr({"type": "array", "items": {}}, "One row per trade."),
         "closedFrom": s("Applied first day, yyyy-MM-dd."),
         "closedTo": s("Applied last day, yyyy-MM-dd."),
         "sortedBy": STR, "direction": STR, **PAGE,
     })),

    # --- Data -------------------------------------------------------------
    ("GetTradeLog", "Get trade log",
     "Individual trades of a backtest or portfolio. Supply exactly one of the three ids. Rows "
     "are arrays; tradeColumns names the columns.",
     obj({
         "runId": s("Id of a run. Alternative to the other ids."),
         "savedBacktestId": s("Id of a saved backtest. Alternative to the other ids."),
         "savedPortfolioId": s("Id of a saved portfolio. Alternative to the other ids."),
         "outcome": s("winners or losers; omit for all."),
         "reasonClosed": s("e.g. Profit Target or Stop Loss."),
         "strategyIds": arr(STR, "Portfolio only: filter by strategy ids."),
         "sortBy": s("opened (default), closed, profit, maxLoss or maxProfit."),
         "direction": s("desc (default) or asc."),
         "limit": s("Trades per page, default 1000, max 5000.", "integer"),
         "offset": OFFSET,
     }),
     obj({
         "tradeColumns": arr(STR, "Column names of the rows in trades."),
         "trades": arr({"type": "array", "items": {}}, "One row per trade."),
         "sortedBy": STR, "direction": STR, **PAGE,
     })),
    ("GetEquityCurve", "Get equity curve",
     "Daily equity curve, at most two years per call. Supply exactly one of the three ids.",
     obj({"parameters": obj({
         "runId": s("Id of a run."),
         "savedBacktestId": s("Id of a saved backtest."),
         "savedPortfolioId": s("Id of a saved portfolio."),
         "seriesStart": s("First day, yyyy-MM-dd."),
         "seriesEnd": s("Last day, yyyy-MM-dd; at most two years after seriesStart."),
     }, ["seriesStart", "seriesEnd"])}, ["parameters"]),
     obj({
         "seriesStart": STR, "seriesEnd": STR,
         "pointColumns": arr(STR, "Column names of the rows in points."),
         "points": arr({"type": "array", "items": {}}, "One row per trading day."),
         "note": NOTE,
     })),
    ("ListTools", "Get MCP server tool list",
     "Calls tools/list on the MCP server (not a tool call). raw contains the complete tool list "
     "as unchanged JSON text, e.g. to detect changes on the server.",
     obj({}),
     obj({
         "toolCount": s("Number of tools.", "integer"),
         "toolNames": arr(STR, "Tool names, alphabetical."),
         "tools": arr({"type": "object"}, "Tool definitions (name, description, inputSchema …)."),
         "raw": s("Raw response: the complete tool list as JSON text."),
     })),
    ("GetUsageLimits", "Get usage limits",
     "Backtests and optimizations remaining today.",
     obj({}),
     obj({
         "backtests": obj({"used": INT, "dailyLimit": INT, "remaining": INT}),
         "optimizations": obj({"used": INT, "dailyLimit": INT, "remaining": INT}),
         "resetsAt": STR,
     })),
]


def to_snake(name):
    return "".join("_" + c.lower() if c.isupper() else c for c in name).lstrip("_")


def build_swagger():
    paths = {}
    for op_id, summary, description, request, response in TOOLS:
        paths[f"/tools/{to_snake(op_id)}"] = {"post": {
            "operationId": op_id,
            "summary": summary,
            "description": description,
            "consumes": ["application/json"],
            "produces": ["application/json"],
            "parameters": [{
                "name": "body",
                "in": "body",
                "required": True,
                "schema": request,
            }],
            "responses": {
                "200": {"description": "Tool result", "schema": response},
                "default": {"description": "Error from the tool or the MCP server"},
            },
        }}

    return {
        "swagger": "2.0",
        "info": {
            "title": "Option Omega",
            "description": "OptionOmega backtests, portfolios and optimizations via its MCP server.",
            "version": "1.0",
        },
        "host": "mcp.optionomega.com",
        "basePath": "/",
        "schemes": ["https"],
        "consumes": ["application/json"],
        "produces": ["application/json"],
        "paths": paths,
        "securityDefinitions": {"oauth2-auth": {
            "type": "oauth2",
            "flow": "accessCode",
            "authorizationUrl": "https://authkit.optionomega.com/oauth2/authorize",
            "tokenUrl": "https://authkit.optionomega.com/oauth2/token",
            "scopes": {"openid profile email offline_access": "openid profile email offline_access"},
        }},
        "security": [{"oauth2-auth": ["openid profile email offline_access"]}],
    }


def build_properties():
    return {"properties": {
        "connectionParameters": {"token": {
            "type": "oauthSetting",
            "oAuthSettings": {
                "identityProvider": "oauth2",
                "clientId": "<CLIENT_ID>",
                "scopes": ["openid profile email offline_access"],
                "redirectMode": "GlobalPerConnector",
                "redirectUrl": "https://global.consent.azure-apim.net/redirect",
                "properties": {"IsFirstParty": "False"},
                "customParameters": {
                    "authorizationUrl": {"value": "https://authkit.optionomega.com/oauth2/authorize"},
                    "tokenUrl": {"value": "https://authkit.optionomega.com/oauth2/token"},
                    "refreshUrl": {"value": "https://authkit.optionomega.com/oauth2/token"},
                },
            },
        }},
        "iconBrandColor": "#1F3A5F",
        "scriptOperations": [op_id for op_id, *_ in TOOLS],
        "capabilities": [],
        "publisher": "Community",
        "stackOwner": "OptionOmega",
    }}


if __name__ == "__main__":
    (OUT_DIR / "apiDefinition.swagger.json").write_text(
        json.dumps(build_swagger(), indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "apiProperties.json").write_text(
        json.dumps(build_properties(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(TOOLS)} actions written.")
