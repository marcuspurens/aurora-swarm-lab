# Voice Gallery schema (EBUCore+ aligned)

Voice Gallery lagras som JSON i `voice_gallery.json`. Det här är en praktisk, utökad
metadata‑profil som är **EBUCore+ aligned** men inte full JSON‑LD/EBUCore+ 2.0.

## Fält per person/voiceprint
- `voiceprint_id` (string, required)
- `person_id` (string, auto)
- `given_name` (string)
- `family_name` (string)
- `display_name` (string)
- `full_name` (string)
- `title` (string)
- `role` (string)
- `roles` (list of strings)
- `affiliation` (string)
- `organizations` (list of strings)
- `aliases` (list of strings)
- `tags` (list of strings)
- `notes` (string)
- `birth_date` (string)
- `death_date` (string)
- `gender` (string)
- `nationality` (string)
- `language` (string)
- `country` (string)
- `city` (string)
- `bio` (string)
- `homepage` (string)
- `image` (string)
- `same_as` (list of strings)
- `identifiers` (list of objects)
- `contacts` (list of objects)
- `socials` (list of objects)
- `credits` (object)
- `source_refs` (object)
- `confidence` (number)
- `ebucore` (object, för rå/kompletterande EBUCore+ data)

## Exempel (praktisk JSON)
```json
{
  "voiceprint_id": "vp1",
  "person_id": "person_vp1",
  "display_name": "Socialdemokraterna",
  "tags": ["auto-suggested", "youtube-channel"],
  "identifiers": [{ "scheme": "party", "value": "S" }],
  "source_refs": { "youtube": "channel-1" },
  "ebucore": {
    "id": "urn:se:party:S",
    "type": "ec:Organisation",
    "ec:name": { "@value": "Socialdemokraterna", "@language": "sv" },
    "skos:notation": "S",
    "dct:identifier": "S"
  }
}
```

## Notering om JSON‑LD
Om du vill spara full JSON‑LD/EBUCore+ 2.0 kan du lägga hela strukturen i
`ebucore`‑fältet utan att förlora data. Vi validerar inte JSON‑LD just nu.

## Indexering
- Embeddings: text + metadata + `ebucore` vektoriseras för semantisk sök.
- GraphRAG: `ebucore` JSON‑LD blir entities/relations i graph‑index.
