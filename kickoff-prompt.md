# Kickoff prompt

Put `CLAUDE.md` in the repo root first, then paste everything below the line.

---

Read `CLAUDE.md` in full before doing anything. It is the standing spec for
this repo and its Hard rules section is binding.

We are starting at **Phase 0**. Do not write application code, do not scaffold
the Flask app, do not create Docker or Kubernetes files. Phase 0 produces
findings and two throwaway scripts, nothing more.

Deliverables for this session, in order:

1. **A short plan** of how you intend to tackle Phase 0. Show me before
   starting.
2. **`.gitignore`**, per section 14, committed before any other file exists.
3. **Capture script.** One live `GET /group/memberlist` call. Writes raw JSON
   to a gitignored directory. Prints **only the key names present**, never
   values, plus counts. I will run it myself — you will not have credentials.
   Make it obvious how to run and what environment variables it needs.
4. **Scrubber.** Turns a capture into a committable fixture: fake names, ssno,
   addresses, emails and phone numbers; structure and value shapes preserved.
   Idempotent, and it must fail loudly rather than silently pass anything
   through that looks like personal data.
5. **Findings document** answering the Phase 0 questions in section 7 —
   payment field semantics, guardian field names, `unit_type` and `roles`
   values, and whether any troop ID appears.
6. **troop_id resolution proposal.** Options with a recommendation.
7. **Arrangemang / attendance spike.** Written analysis only. How many keys
   would a term of weekly meetings need? Is programmatic creation possible at
   all? Options with a recommendation. No code.

Stop after the plan and wait for me. Stop again after the capture script and
wait for me to run it — everything downstream depends on real data, and I do
not want you guessing at field semantics in the meantime.

Ask me anything that is genuinely ambiguous rather than assuming. In
particular, the age bracket configuration in section 12 is deliberately
unspecified — I will provide it later. Design the schema to be general and do
not invent brackets.
