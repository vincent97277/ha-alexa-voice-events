# Choose and verify recognized phrases

Use this guide when a voice query sometimes does nothing, or before adding a new
phrase to the Blueprint. It applies to both v0.2.0 and v0.3.0.
Keep the component and imported Blueprint on the same fixed version; this guide
does not require changing versions.

## Start with a clear phrase

Choose a natural phrase that gives the important word some context. For example,
try “where is the fridge” rather than the isolated word “fridge”. This is a phrase
design suggestion, not a built-in command. Alexa still chooses its native response;
the integration only observes the resulting recognized text.

For a sensor query, a phrase such as “check the room climate” is a candidate to test
with your own voice and speaker. No phrase, minimum word count or speaker model is
guaranteed. Adding filler words alone does not establish better recognition.

1. Keep language, speaker distance and background noise consistent. Let the previous
   exchange finish before the next trial, and use the wake word each time.
2. Say the candidate once. If nothing happens, do not immediately repeat it: a second
   utterance makes it harder to pair the audible result with the correct event.
3. Inspect the selected voice event's `voice_command` and source time, then the
   automation trace. A previous event left on screen is not a new recognition.
4. Add the exact text to **Recognized phrases**, one phrase per line. Include the
   wake word only in variants where it appears in the actual text. Matching ignores
   case and repeated whitespace; it does not infer intent, correct spelling, remove
   punctuation or translate phrases.
5. Test each candidate repeatedly, pairing every attempt with its own event and
   trace. Before calling a setup verified, get at least three consecutive complete
   results with acceptable response time. Record failures too; three successes do
   not establish a general reliability rate.

Adding a phrase in HA does not register it with Amazon, train Alexa or reserve it
against Alexa's built-in functions. Use separate, non-overlapping phrases for
independent automations.

## Identify the failing stage

| Evidence | Meaning | Next step |
| --- | --- | --- |
| Amazon history says No transcript | No usable recognition text exists for that attempt | Investigate recognition or listening conditions; phrase aliases cannot recover missing text |
| No new AVE event | Recognition, upstream delivery, reception or freshness may be involved | Check Amazon history and reception diagnostics; do not infer No transcript from event absence alone |
| New event has different text; trace exits at phrase matching | No matched household action or managed Speak was requested | Prefer a clearer phrase, or intentionally add an acceptable literal variant |
| Phrase matched; a guard or target check rejects it | Local authorization, freshness or routing stopped the step | Read `voice_guard_reason`, resolver reasons and `reply_reason` in the trace |
| Trace calls Speak; speech is missing or incomplete | Local service submission is established, audible completion is not | Save the exact trial and compare Speak-only with Stop plus Speak; report both trace and audible result |

An audible start/end tone alone does not establish which stage failed, whether
Follow-Up Mode was active or whether a Speak request was delivered. A successful
trace is not an Amazon playback receipt. See [reply limits](replies.md#failures-and-honest-outcomes).

Do not globally replace near-sounding words such as bridge with fridge. They may
be different intended requests. A household alias is an explicit choice, and it
still cannot help when Amazon supplies no text. The receiver preserves the final
recognized text and does not replay an older command to fill a gap.

## Why context can help

Amazon describes ASR systems that score competing word sequences using linguistic
context, and systems that rerank candidate transcriptions after the utterance.
This supports a practical reason to try a clear complete phrase: more relevant
context can help resolve similar sounds. It does not prove which model a particular
speaker uses, that it first made an error and then corrected it, or that longer
utterances always perform better.

Sources:

- [Amazon Science: Contextual clues and Alexa speech recognition](https://www.amazon.science/blog/contextual-clues-can-help-improve-alexas-speech-recognizers)
- [Amazon Science: Candidate transcriptions and language-model reranking](https://www.amazon.science/blog/on-device-speech-processing-makes-alexa-faster-lower-bandwidth)
- [Amazon: Similar-sounding names and overlap with native functions](https://developer.amazon.com/en-US/blogs/alexa/alexa-skills-kit/2021/11/avoid-overlaps-when-choosing-an-invocation-name-for-your-alexa-skill)

The last source concerns Custom Skill naming. Its overlap guidance is relevant to
phrase selection; it does not mean this Blueprint has a Custom Skill interaction
model. Claims about on-device processing also do not establish that architecture
on a third-party speaker.

## When a history listener is not enough

If you need Alexa to route a request to your own handler, evaluate an explicit
[Alexa Routine](https://developer.amazon.com/en-US/alexa/alexa-haus/routines) with
supported [HA Smart Home entities, scenes or scripts](https://www.home-assistant.io/integrations/alexa.smart_home/),
or a Custom Skill. Those are separate setup paths with their own requirements;
recognition can still fail. They are not installed by Alexa Voice Events and do not
automatically reproduce its dynamic sensor replies or source-speaker selection.
