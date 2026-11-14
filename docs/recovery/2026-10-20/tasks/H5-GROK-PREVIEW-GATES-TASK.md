# Preserve the G6 preview behind the release gates

The Windows candidate for afd5909 failed the SDK import guard and the product-neutral
request-path guard. An isolated run found three failures across the registry, failure
classification and grant preview. Fix the source of those failures. Keep the guards,
frozen graph arguments, marked step IDs, ordinary previews and offline artifact witnesses.
Prepare a separate candidate. The owner requested installation of afd5909 specifically.
