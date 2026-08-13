---
name: olira-actions
description: Register outbound-action webhook or email destinations, subscribe them to triggers, set up digest batching, verify Olira-Signature HMAC on webhook deliveries, and rotate signing secrets — via the Olira SDK (Python or C#), not the `olira` CLI (there is no CLI command for this).
---

# Olira Outbound Actions

Installed as `olira` (verify with `olira --version`; this doc matches v{{VERSION}}),
but outbound actions has **no `olira` CLI command** — there is no shell equivalent
to reach for here. Everything below is
Python (`olira` on PyPI) or C# (`Olira` on NuGet) SDK code, or a raw REST call
under `/v1/actions/*`. If a task needs a destination created, a trigger changed,
or a delivery inspected, write or run SDK code — don't look for an `olira actions`
subcommand, it doesn't exist.

Auth for this surface is the same **API key** class as every other Olira SDK
call (see `olira-setup`), scoped `sdk:actions`.

## Destinations and triggers

A **destination** is a webhook URL or an email address; a **trigger** is the
event that causes a delivery to it. Currently available triggers:

| Trigger | Fires when |
|---|---|
| `patient.state.changed` | Something changed about a patient, such as new symptoms, lab results, or medications |
| `log.no_state_change` | Olira received a log for a patient, but it didn't change anything known about them |
| `org.mapping.failed` | One of your incoming logs could not be translated into Olira's data model |
| `ingestion.completed` | A historical ingestion job you started finished successfully |
| `ingestion.failed` | A historical ingestion job you started did not finish successfully |

Pass `["*"]` (or `ActionTrigger.ALL` / `ActionTrigger.All`) to subscribe to every
currently available trigger. Because `"*"` is evaluated by the platform rather
than by this list, a `"*"` subscription could start receiving additional trigger
types later without another call. Nothing validates a trigger client-side — a
typo'd string still reaches the server as a 422.

Python takes `config=` (one of the two config classes below). C# takes
`webhookConfig:` **or** `emailConfig:`, never both, never a unified `config:`.

A webhook `url` must be public HTTPS. `http://`, `localhost`, and
private/internal addresses are rejected, both when you set the URL and again
every time Olira sends to it — do not use `http://localhost:...`.

```python
import olira
from olira import ActionTrigger, WebhookDestinationConfig, EmailDestinationConfig

olira.init(api_key="YOUR_API_KEY")

destination = olira.create_action_destination(
    config=WebhookDestinationConfig(url="https://hooks.example.com/olira"),
    subscribed_triggers=[ActionTrigger.PATIENT_STATE_CHANGED, ActionTrigger.INGESTION_FAILED],
)
print(destination.signing_secret)  # shown once, store it now

email_destination = olira.create_action_destination(
    config=EmailDestinationConfig(to_email="ops@acme.example"),
    subscribed_triggers=[ActionTrigger.INGESTION_FAILED],
)
print(email_destination.signing_secret)  # shown once, store it now
```

```csharp
using Olira;

OliraModule.Init(apiKey: "YOUR_API_KEY");

var destination = OliraModule.CreateActionDestination(
    webhookConfig: new WebhookDestinationConfig { Url = "https://hooks.example.com/olira" },
    subscribedTriggers: [ActionTrigger.PatientStateChanged, ActionTrigger.IngestionFailed]);
Console.WriteLine(destination.SigningSecret); // shown once, store it now

var emailDestination = OliraModule.CreateActionDestination(
    emailConfig: new EmailDestinationConfig { ToEmail = "ops@acme.example" },
    subscribedTriggers: [ActionTrigger.IngestionFailed]);
Console.WriteLine(emailDestination.SigningSecret); // shown once, store it now
```

The signing secret is returned once, at creation. Store it immediately — it can
be rotated later (`rotate_action_destination_secret` / `RotateActionDestinationSecret`)
but never read back. During rotation the old secret stays valid for 24 hours
(the `Olira-Signature` header carries both).

## Delivery volume: one per event, by default

Subscribing a destination to a high-frequency trigger like `patient.state.changed`
does not batch anything on its own: 50 patients changing state in the same minute
is 50 separate deliveries — 50 webhook calls, or 50 emails. That is rarely what
you want for an email destination. Decide up front whether you want immediate
delivery (the default) or batched delivery before going live, not after the
volume surprises someone.

## Digest batching

Opt a destination into batching a trigger's deliveries into one summary per day
instead of one per event, via `digest_schedule` / `digestSchedule`:

```python
from olira import DigestSchedule

olira.update_action_destination(
    destination.id,
    digest_schedule=DigestSchedule(
        time_of_day="09:00",  # "HH:MM", on a half-hour boundary
        timezone="America/New_York",
        triggers=["patient.state.changed"],  # must be a subset of subscribed_triggers
    ),
)
```

```csharp
OliraModule.UpdateActionDestination(
    destination.Id,
    digestSchedule: new DigestSchedule
    {
        TimeOfDay = "09:00", // "HH:MM", on a half-hour boundary
        Timezone = "America/New_York",
        Triggers = ["patient.state.changed"], // must be a subset of SubscribedTriggers
    });
```

`patient.state.changed` is the trigger worth batching for most destinations —
`RECOMMENDED_DIGEST_TRIGGERS` / `ActionTrigger.RecommendedDigestTriggers` names
it explicitly. The other triggers are already low-frequency enough that
immediate delivery works well. Digest deliveries aren't instant: a trigger
enabled for batching sits buffered until the destination's `time_of_day` /
`TimeOfDay` next arrives in its timezone, which can be close to a full day
later — don't poll for a quick result the way you would for an immediate
trigger.

## Verifying webhook deliveries

Webhook deliveries carry an `Olira-Signature` header: `t=<unix_ts>,v1=<hex_hmac>`.
Email deliveries do not — skip this section for email. Recompute the HMAC with
the destination's signing secret and compare. Reject a missing or malformed
timestamp, one too far in the past (replay), or one unreasonably far in the
future (clock skew or forgery) **before** checking the signature at all. During
secret rotation the header carries **two** `v1=` entries; check if any matches,
don't assume there's exactly one.

Copy this function as-is. Do not reimplement it from the description above.

```python
import hashlib
import hmac
import time


def verify_signature(secret: str, header: str, raw_body: bytes, *, max_skew_seconds: int = 300) -> bool:
    fields = dict(part.split("=", 1) for part in header.split(",") if part.startswith("t="))
    try:
        timestamp = int(fields["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - timestamp) > max_skew_seconds:
        return False
    signatures = [part.split("=", 1)[1] for part in header.split(",") if part.startswith("v1=")]
    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)
```

```csharp
using System.Linq;
using System.Security.Cryptography;
using System.Text;

static bool VerifySignature(string secret, string header, byte[] rawBody, int maxSkewSeconds = 300)
{
    var parts = header.Split(',');
    var tPart = parts.FirstOrDefault(p => p.StartsWith("t="));
    if (tPart is null || !long.TryParse(tPart.Substring(2), out var timestamp))
        return false;
    if (Math.Abs(DateTimeOffset.UtcNow.ToUnixTimeSeconds() - timestamp) > maxSkewSeconds)
        return false;

    var signatures = parts.Where(p => p.StartsWith("v1=")).Select(p => p.Substring(3));

    using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
    var signedPayload = Encoding.UTF8.GetBytes($"{timestamp}.").Concat(rawBody).ToArray();
    var expected = Convert.ToHexString(hmac.ComputeHash(signedPayload)).ToLowerInvariant();

    return signatures.Any(sig => CryptographicOperations.FixedTimeEquals(
        Encoding.UTF8.GetBytes(expected), Encoding.UTF8.GetBytes(sig)));
}
```

`raw_body`/`rawBody` must be the exact bytes as received, before any JSON
parsing — parsing to a dict and re-serializing changes whitespace and breaks
the signature. Get it before your framework's body-parsing middleware runs:

```python
# Flask
raw_body = request.get_data()  # not request.get_json()
# FastAPI
raw_body = await request.body()
```

```csharp
// ASP.NET Core — enable buffering so the body can still be read downstream
Request.EnableBuffering();
using var ms = new MemoryStream();
await Request.Body.CopyToAsync(ms);
var rawBody = ms.ToArray();
Request.Body.Position = 0;
```

## Inspecting and redelivering

```python
deliveries = olira.list_action_deliveries(destination_id=destination.id, status="dead_letter")
for d in deliveries.data:
    olira.redeliver_action_delivery(d.id)  # 409 if the destination is disabled — re-enable it first
```

```csharp
var deliveries = OliraModule.ListActionDeliveries(destinationId: destination.Id, status: "dead_letter");
foreach (var d in deliveries.Data)
{
    OliraModule.RedeliverActionDelivery(d.Id); // 409 if the destination is disabled — re-enable it first
}
```

## Scope

| Scope | Grants |
|---|---|
| `sdk:actions` | Create, read, update, and delete outbound-action destinations and their signing secrets; read and redeliver delivery history |
