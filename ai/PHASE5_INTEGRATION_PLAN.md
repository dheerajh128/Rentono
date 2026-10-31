# Rentono — Phase 5: Smart AI Search Integration Plan

Read-only audit of the repository as it exists, plus the approved shape of the Node.js integration. This document is the implementation brief. It does not change application behavior.

The website and the AI service are separate processes that already share MongoDB. Normal search is a title-only regex. The AI service returns ranked listing DTOs. The integration adds a second search action: Express calls FastAPI, then reloads those listings from MongoDB before rendering.

Nothing in this audit was implemented. The Express app and the AI API were not started, and the Python tests were not executed.

---

## A. Repository map

Rentono is a CommonJS Express app. `package.json` has no `"type": "module"`, pins Node `22.18.0`, and its `test` script exits with an error. There is no start script. The process entry is `app.js`, which listens on port **8080**.

Dependencies that matter for this work: Express 4, EJS, ejs-mate, Mongoose 9, Joi, Passport, connect-flash, connect-mongo, Multer, and Cloudinary. There is no HTTP client package. Node 22’s global `fetch` is the client to use.

| Path | Responsibility |
| --- | --- |
| `app.js` | Loads `.env` unless `NODE_ENV` is `production`. Connects Mongoose with `ATLAS_URL`, sessions (`SECRET`, Mongo store), Passport, flash, and EJS. Mounts routes. 404 and error handlers. |
| `routes/listings.js` | Listing routes, including search and category filters. |
| `controllers/listings.js` | Listing queries and renders. |
| `models/listing.js` | Listing schema. No virtuals or instance methods. |
| `models/review.js` | Comment, rating 1–5, author. |
| `models/user.js` | Email, optional `googleId`, passport-local-mongoose (`username`). |
| `middleware.js` | `isLoggedIn`, `isOwner`, `isAuthor`, Joi validation. Search is public. |
| `schema.js` | Joi for creating and updating listings and reviews. No search schema. |
| `views/layouts/boilerplate.ejs` | Navbar, flash, footer, Bootstrap, `/css/style.css`, `/js/script.js`. |
| `views/includes/navbar.ejs` | The only search form. |
| `views/listings/lists.ejs` | Index and category grid, including the tax toggle. |
| `views/listings/search.ejs` | Title-search results. Card markup is copied here, not shared. |
| `views/listings/eachlist.ejs` | Detail page. Expects a populated Mongoose document. |
| `public/css/style.css` | Card, navbar, and footer layout. |
| `public/js/script.js` | Bootstrap form validation only. |
| `public/js/map.js` | Mapbox on the detail page. Needs `geometry.coordinates`. |
| `routes/users.js`, `routes/reviews.js` | Auth and reviews. Outside this integration. |
| `init/index.js`, `init/dbss.js` | Local seed into `mongodb://127.0.0.1:27017/rentono`. Those sample listings have no `category` or `geometry`. |
| `ai/` | FastAPI, LangGraph, FastMCP, Motor. Read-only against MongoDB. |

Environment names used by code, without values:

- Website: `ATLAS_URL`, `SECRET`, `MAP_TOKEN`, `CLOUD_NAME`, `CLOUD_API_KEY`, `CLOUD_API_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `NODE_ENV`
- AI service: `ATLAS_URL`, `DB_NAME`, `GROQ_API_KEY`, optional `AI_PORT` (default **8000**)

`.gitignore` ignores `.env`. There is no `AI_API_URL` yet.

`ai/README.md` is behind the code. It still mentions files that are not in the tree, and it still names Llama 3.3. `ai/services/llm_service.py` uses `openai/gpt-oss-120b`. The source files cited below are the contract.

---

## B. Current search flow

There is one text search and two other listing browsers. They do not combine.

### 1. Title search

The navbar form in `views/includes/navbar.ejs` is `GET /listings/search` with a single field, `search`. The placeholder says “Search Destination”. The controller searches `title`, not location.

`routes/listings.js` registers `GET /search` before `GET /:id`, so the word `search` is not treated as an id. `controllers/listings.js` `searchListings` does this:

```js
module.exports.searchListings = async (req, res) => {
    let { search } = req.query;
    let searchedListings = await Listing.find({
        title: { $regex: search, $options: "i" }
    });
    res.render("listings/search.ejs", { searchedListings, search });
}
```

There is no trim, length check, regex escape, category, price, country, sort, or pagination. An empty submission sends `search=` and that regex matches every title. The query string is passed straight into `$regex`.

`views/listings/search.ejs` receives `search` and `searchedListings`. Each card uses:

- `list._id` → link `/listings/<%= list._id %>`
- `list.image.url`
- `list.title`
- `list.price.toLocaleString("en-IN")`, prefixed with `&#8377;` and suffixed with `/night`

An empty array renders “No Listings Found”. Location, category, rating, and review count are not shown. This template has its own card CSS. It does not include the category bar or the tax toggle.

### 2. Index

`GET /` sets a flash message and redirects to `GET /listings`. `index` loads every listing with `Listing.find({})` and renders `views/listings/lists.ejs` with `selectedCategory: ""`.

### 3. Category filters

The same `lists.ejs` links to `GET /listings/category/:category`. `filterByCategory` uses an exact `category` match and renders `lists.ejs` again. Categories are:

`Rooms`, `Iconic Cities`, `Mountains`, `Castles`, `Pools`, `Camping`, `Farms`, `Arctic`

“Trending” is the unfiltered index. The tax switch is client-side only: it reveals a “+18% GST” label and does not change the stored price.

### 4. Detail page

`GET /listings/:id` calls `showNewForm`, which `findById`s the listing and populates `reviews.author` and `owner`. A missing listing flashes an error and redirects to `/listings`.

`views/listings/eachlist.ejs` needs `owner.username`, `owner._id.equals(...)`, a `reviews` array, and `geometry.coordinates` for Mapbox. It also injects the document with `<%- JSON.stringify(eachList) %>`. Those are Mongoose behaviors. A plain AI object would throw on this page.

### Errors and request parsing

`utilities/wrapAsync.js` forwards rejected promises to the handler in `app.js`. That handler logs the full error and renders `views/error.ejs` with `<%= message %>`. Flash text is escaped in `views/includes/flash.ejs`. `app.js` parses URL-encoded bodies only. There is no `express.json()`.

### Behaviors that stay unchanged

- `GET /listings/search?search=` remains a case-insensitive title regex, including its empty-input behavior.
- Category links, the index, the tax toggle, card links, and the detail route stay as they are.
- Search stays public.
- Prices stay in rupees, formatted with `en-IN`, labeled per night.
- Detail pages keep loading the listing themselves. AI results only need a real id in the card link.

---

## C. AI service contract

`ai/main.py` is the HTTP app. `serve()` binds **127.0.0.1** and `AI_PORT` (default 8000).

### `GET /health`

Returns `{"status":"ok"}`. It does not call Groq or MongoDB.

### `POST /ai/search`

Request body:

```json
{ "query": "<text>" }
```

The query is trimmed, must be non-empty, and must be at most 500 characters. Blank, missing, and over-long queries return **422** and never call the agent. That behavior is asserted in `ai/test_api.py`. Those tests were read, not run, for this audit.

A completed agent run returns **200**. Confirmed shape from `SearchResponse` and `ai/test_api.py`:

```json
{
  "query": "peaceful mountain stay in India under 5000",
  "intent": {
    "category": "Mountains",
    "min_price": null,
    "max_price": 5000,
    "location": null,
    "country": "India",
    "preferences": ["peaceful", "great reviews"]
  },
  "results": [
    {
      "_id": "69485099aaaaaaaaaaaaaaaa",
      "title": "Cedar Cabin",
      "description": "A quiet cabin",
      "price": 4200,
      "location": "Manali",
      "country": "India",
      "category": "Mountains",
      "image": { "url": "https://example.com/cabin.jpg", "filename": "cabin.jpg" },
      "geometry": { "type": "Point", "coordinates": [77.1, 32.2] },
      "rating": 4.6,
      "review_count": 8,
      "score": 0.86,
      "reason": "The description says it is a quiet cabin."
    }
  ],
  "summary": "Cedar Cabin in Manali is listed at INR 4200 per night.",
  "error": null
}
```

`response_model_by_alias=True` serializes the Mongo id as `_id`.

Nullable fields: `intent`, `description`, `geometry`, `image.filename`, `rating`, `score`, `reason`, `summary`, `error`. `review_count` can be `0`. `preferences` defaults to `[]`.

### Agent pipeline

`ai/agent/graph.py`: parse intent → retrieve → rank → explain.

Retrieval is the MCP tool `search_listings` in `ai/mcp_server/tools.py`, which calls `ai/services/listing_service.py`. Filters are only:

- `category` (canonical enum, exact match)
- `min_price` / `max_price`
- `location` (escaped, case-insensitive substring)
- `country` (escaped, case-insensitive substring)

`preferences` are ranking hints, not query filters. An unsupported category returns no rows. The agent asks for at most 10 listings (`SEARCH_LIMIT` in `ai/agent/nodes.py`). The tool also caps `limit` at 50.

Ratings are computed with a `$lookup` on `reviews`. They are not stored on the listing. `score` is 0–1, or `null` when ranking falls back to Mongo order. A model `reason` that is not grounded in stored fields is replaced with a factual sentence.

### HTTP 200 agent errors

These still return HTTP 200, with `results: []` and `error` set:

| `error` | Meaning |
| --- | --- |
| `intent_parse_failed` | The query could not be parsed. |
| `unsupported_category: <name>` | Category is outside the enum. |
| `mcp_search_failed` | The listing tool failed. |
| `mcp_response_invalid` | The tool payload was not a listing list. |
| `invalid_query` | Empty query inside the graph. The HTTP layer rejects blanks first, so Express should not see this when it validates the same way. |

`summary` explains those cases in plain text. An empty match with `error: null` uses a “No listings matched this search…” summary.

### HTTP 500

An unexpected exception returns **500** and exactly:

```json
{ "detail": "The search could not be completed." }
```

The handler logs a redacted traceback and does not put the exception in the response.

### Persistence details

- Listing ids in the service are `str(doc["_id"])`.
- Image data is copied from `image.url` and `image.filename`.
- Geometry, when present, is GeoJSON `[longitude, latitude]`.
- Motor uses the collections `listings` and `reviews`, matching Mongoose’s default plural names.
- Motor selects the database with `DB_NAME`. Mongoose uses the database named in `ATLAS_URL`.

---

## D. Compatibility findings

The AI payload is a Pydantic DTO serialized to JSON. It is not a Mongoose document.

| Website expectation | AI result |
| --- | --- |
| `list._id` in `/listings/:id` | `_id` is a 24-character hex string. `findById` accepts that. |
| `list.image.url` | Same `{ url, filename }` object. Uploads store a Cloudinary URL. The seed file stores Unsplash URLs. The DTO copies whichever string is in Mongo. |
| `list.price.toLocaleString("en-IN")` and a hardcoded rupee sign | `price` is a JSON number. There is no currency field. Reasons say “INR”. |
| `list.title` | Present. |
| Location, category, rating on cards | Not rendered today. The DTO has `location`, `country`, `category`, computed `rating`, and `review_count`. |
| `score`, `reason` | Extra fields. Current templates never read them. |
| Detail page `owner`, `reviews`, `.equals`, `geometry` | Absent from the search DTO. `get_listing_by_id` also does not populate `owner`. |

`views/listings/search.ejs` could draw a card from a DTO because it only reads `_id`, `image.url`, `title`, and `price`. Display fields still come from MongoDB. A bad or stale response could change the price, title, or image URL. The detail page cannot be rendered from the DTO: it needs populated `owner`, `reviews`, and Mongoose `ObjectId.equals`.

### Rendering rule

1. Take `_id` values from `results`, and only when each id is a 24-hex string.
2. Load them with `Listing.find({ _id: { $in: ids } })`.
3. Reorder the documents to match `results`. Mongo `$in` does not preserve rank order.
4. Take title, price, image, location, and category from those documents.
5. Take `summary`, `score`, and `reason` from the API only after the type checks in section E.
6. Ignore every other payload field for rendering.
7. Card links go to the existing `GET /listings/:id` route. That route loads the detail page itself.
8. Do not construct fake Mongoose documents.
9. Do not render `eachlist.ejs` from the AI payload.

`score` and `reason` belong only on the new AI results template. Index and title-search templates stay untouched, so those fields cannot affect existing cards.

### Database-name check before coding

`ai/db/client.py` uses `client[settings.DB_NAME]`. `app.js` uses the database inside `ATLAS_URL`. If those names differ, smart search and the website read different data. Confirm they match before implementation. Do not paste the connection string into chat, logs, or this file.

---

## E. Proposed integration

Title search stays on `GET /listings/search`. Add a second navbar button, **Smart search**, on the same form, with `formaction="/listings/ai-search"`. The existing button keeps `action="/listings/search"` and the field name `search`.

```text
Navbar
  Search        -> GET /listings/search?search=...
                   unchanged title regex

  Smart search  -> GET /listings/ai-search?search=...
                   Express trims and checks length (1–500)
                   POST {AI_API_URL}/ai/search
                   body: {"query":"<trimmed text>"}
                   FastAPI -> LangGraph -> MCP -> MongoDB
                   Express checks the JSON
                   Listing.find({ _id: { $in: validIds } })
                   reorder to match results[]
                   render views/listings/ai-search.ejs

Card link       -> GET /listings/:id
                   existing detail route
```

`AI_API_URL` defaults to `http://127.0.0.1:8000`. Use `127.0.0.1`, not `localhost`, because `serve()` listens on `127.0.0.1`. The path `/ai/search` is appended in code. The browser never receives this URL, the Groq key, or the Mongo URL.

### Handler steps

1. Read `req.query.search`. Trim it. Empty or longer than 500 characters renders the AI page with a fixed validation message and does not call FastAPI.
2. `fetch` with `AbortSignal.timeout(20000)`. The agent can make three model calls. Twenty seconds is the starting timeout.
3. Accept only HTTP 200 JSON whose `results` value is an array.
4. Keep an item only when `_id` matches `/^[a-fA-F0-9]{24}$/`.
5. Keep `score` only when it is a finite number from 0 through 1. Otherwise treat it as absent.
6. Keep `reason` and `summary` only when they are strings.
7. Load the surviving ids with `Listing.find`. Restore AI order. Skip ids that are no longer in the database.
8. Skip a document that has no `image.url`, so one bad document cannot crash the page.
9. Render `views/listings/ai-search.ejs`.

The new template copies the card markup and card CSS from `views/listings/search.ejs`, then adds:

- the escaped summary above the grid
- per card, the escaped reason
- the score when it survived the type check
- location and category from the re-fetched document

Use `<%= %>`. Do not use `<%- %>` for summary or reason. Do not place model text inside a `<script>` tag. Unknown JSON fields are ignored.

No new npm dependency. No `express.json()`, because the browser still submits a normal GET form. `searchListings` is not modified. Smart search stays public.

---

## F. Files to change

### Required

| File | Change |
| --- | --- |
| `views/includes/navbar.ejs` | Add the Smart search button with `formaction="/listings/ai-search"`. Leave the form `action` and the current Search button as they are. |
| `routes/listings.js` | Register `GET /ai-search` before `GET /:id`. |
| `controllers/listings.js` | Add `aiSearch` only. Do not change `searchListings`, `index`, or `filterByCategory`. |
| `utilities/aiClient.js` | New file. URL resolution, timeout, fetch, and response checks. |
| `views/listings/ai-search.ejs` | New file. Search-card layout plus summary, reason, and score. |

### Optional

| File | Change |
| --- | --- |
| `public/css/style.css` | Only if the second button overflows the 4.5rem navbar. The navbar collapses below the `md` breakpoint. |
| `test/aiClient.test.js` | Node’s built-in test runner, with `fetch` mocked. |

### Leave unchanged

`app.js`, `views/listings/search.ejs`, `views/listings/lists.ejs`, `views/listings/eachlist.ejs`, the models, `middleware.js`, `schema.js`, `package.json`, the lockfile, and `.env`.

Do not extract a shared card partial in this pass. That would edit the existing result pages.

The code default covers a missing `AI_API_URL`, so `.env` does not need an edit for local development. When the variable is set, it must be an `http:` or `https:` URL with no path required from the user. The client appends `/ai/search`.

Run the new test with:

```text
node --test test/aiClient.test.js
```

Leave the `npm test` script alone. It currently exits with an error on purpose.

---

## G. Failure handling and fallback

Title search stays on its own route. A failed smart search does not run that regex. A sentence such as “quiet cabin in Goa under 8000” is not a title, and a title regex would answer a different question.

| Outcome | What the user sees |
| --- | --- |
| HTTP 200, `error: null`, `results` has ids that exist | Summary and cards in AI order. |
| HTTP 200, `error: null`, `results: []` | The summary, and “No Listings Found”. This is a completed search with no matches. |
| HTTP 200 with `unsupported_category`, `intent_parse_failed`, `mcp_search_failed`, or `mcp_response_invalid` | The summary, and no cards. The agent finished. Title search is not run. |
| Well-formed ids that are no longer in Mongo | Those ids are skipped. If none remain, show the summary and an empty list. |
| Connection refused, timeout, non-200, non-JSON, or `results` not an array | A fixed message: smart search is unavailable. A link offers title search for the same text: `/listings/search?search=...`. The user chooses it. |
| Blank input, or more than 500 characters | Fixed validation message. No request to FastAPI. |
| `AI_API_URL` unset | Use `http://127.0.0.1:8000`. |
| `AI_API_URL` set but empty, or not `http:` / `https:` | The same unavailable message. No request is sent. |

The unavailable message does not include `error.message`, the response body, FastAPI’s `detail`, or a stack trace. Server logs may record a short code such as `ai_search_timeout`.

`mcp_search_failed` is an HTTP 200 agent result, not a connection failure. It uses the summary treatment.

A Mongo error during the re-fetch may continue through `wrapAsync`, consistent with title search. The AI HTTP failures are handled inside `aiSearch` and render `ai-search.ejs` instead of `error.ejs`.

---

## H. Test plan

No tests were run for the audit. `ai/test_api.py` already covers the FastAPI contract with a fake agent. The Node app has no test suite.

### Automated (`node --test`, `fetch` mocked)

- A successful body yields ids in order. Score and reason are kept only when valid.
- Empty `results` with `error: null` is a successful empty search, not a transport error.
- HTTP 200 with an agent `error` string is a completed search.
- Connection refusal, aborted timeout, HTTP 500, HTTP 422, invalid JSON, and a missing `results` array become a safe failure. The failure object does not carry the response body.
- A `javascript:` image URL or extra fields in the payload are not used as display data.
- Blank and 501-character queries never call `fetch`.
- Missing `AI_API_URL` resolves to `http://127.0.0.1:8000`.
- A non-HTTP `AI_API_URL` fails before `fetch`.

### Manual (Express on port 8080)

- Title search still returns the same title matches and still ignores location text.
- Category filters, Trending, and the tax toggle still behave as they do now.
- Smart search against a running API renders cards through `ai-search.ejs`, in returned order, with summary and reasons escaped.
- Each card opens the existing detail page, including owner, reviews, and the map.
- A query that matches nothing shows the empty summary and does not also show title-search results.
- With the API stopped, the page shows the fixed unavailable message and the optional title-search link.
- Timeout and non-200 responses show that same unavailable message.
- A query containing HTML is escaped. A stored reason containing HTML is escaped.
- The page source contains no `GROQ_API_KEY`, `ATLAS_URL`, `SECRET`, or stack trace.
- The navbar is checked at a narrow width.

---

## I. Risks and unresolved questions

- `DB_NAME` and the database inside `ATLAS_URL` were not compared. Confirm they name the same database before implementation, without copying the URI into chat or logs.
- The 20-second timeout is an estimate. A live search was not timed in this session.
- `package.json` declares Node `22.18.0`, which has global `fetch`. The `engines` field is not enforced. An older Node would not have `fetch`.
- `ai/README.md` disagrees with the code about the model name and about files that are not present. Trust `ai/services/llm_service.py` and `ai/main.py`.
- Title search still passes raw user input to `$regex`. That behavior stays.
- Existing cards throw if `price` or `image` is missing. Listings created through the current form have both. The AI template skips a document with no `image.url`.
- The second navbar button may wrap inside the fixed navbar height. Check it in the browser.
- `init/dbss.js` seeds a different database and has no categories or coordinates. It is not the fixture for AI search.
- This audit did not prove the API process is running, and it did not re-check any earlier live listing response. The contract above is from the current source and from `ai/test_api.py`.

---

## J. Implementation sequence

1. Add `utilities/aiClient.js` and `test/aiClient.test.js`. Run `node --test test/aiClient.test.js`. No route and no UI in this step.
2. Add `aiSearch`, `GET /listings/ai-search`, and `views/listings/ai-search.ejs`. Request the route directly with the API running, then with the API stopped. Confirm `GET /listings/search` is unchanged.
3. Add the navbar button. In the browser, run title search, a category filter, a successful smart search, an empty smart search, and a detail-page click from an AI card.
4. Walk the failure cases in section H, including a query that contains HTML, and check the navbar at a narrow width.
5. Stop. Do not add payments, trip planning, host features, or a shared card refactor in this pass.

---

## Out of scope

- Calling FastAPI from browser JavaScript
- Replacing or silently rewriting title search
- Duplicating the AI service’s filters or ranking in Express
- Passing AI DTOs into `eachlist.ejs`
- Editing `.env`, lockfiles, or dependencies
- New product areas beyond property search
