# Setup notes (backlog T01)

Each teammate adds one section after running the setup in CONTRIBUTING.md §1. Keep the format.

<!--
## Name · OS · Python version

```
paste the output of:
python src/validate_pack.py
python -m unittest discover -s tests
```

One correct finding: claim ID + rule ID of a FAIL you checked by hand against the claim
One limitation you noticed:
-->



## Malak · Windows 11 · Python 3.12
python src/validate_pack.py
{
"development": {
"claims": 400,
"results": 6000
},
"validation": {
"claims": 150,
"results": 2250
},
"stress": {
"claims": 50,
"results": 750
}
}
PASS: transport, public labels/evidence, CSV round trips, split IDs, mapping basics and release checksums. This is not full HL7 FHIR validation.

python -m unittest discover -s tests
......................................................

Ran 54 tests in 0.182s

OK