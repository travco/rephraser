### RePhraser

#### A Python-based reimagining of [Phraser](https://github.com/Sparell/Phraser) using Markov-chains for linguistically-correct password cracking.

In its current state, it is easily able to kick out more than 3 million candidates per second on a modern quadcore CPU.
In terms of hit rate, combined with the `travco_princev8.rule` a single GPU was able to crack 
45 passwords otherwise-uncracked in any other attack in under an hour. But you know, definitely is still in development. :)

The purpose and idea behind linguistic cracking is that people forced to adhere to long password requirements (e.g. 15 character
 minimum) commonly create passphrases of words that are related. More specifically words that are in a logical order,
 often times choosing sentences or sentence fragments.
By training a model to observe what words generally follow other words in source text, one can produce candidates that make
 some amount of linguistic sense and better mimic human choices. Drastically lowering the number of possible choices, and the
 amount of time it takes to crack four and five word phrases, not to mention making *even longer* phrases feasible to enumerate.

#### Usage:

As with most sane programs, `python3 rephraser.py -h` will list arguments it can take.

1. Get a corpus of sentences (or just a large text, like a text format ebook) to work with, I recommend choosing a file 
 from https://wortschatz.uni-leipzig.de/en/download/ and extracting the "sentences" file inside it (you should remove line
 numbers `sed -r 's/^[0-9]+[[:blank:]]*//' FILE`), as there should only be sentences in that file before giving it to RePhraser).

2. Then call RePhraser on it, piping the output to hashcat (I hope you have sufficient RAM, Markov models are memory-heavy to generate). 
  E.g. :
  `python3 rephraser.py --corpus sentences-eng_wikipedia_2016_1M --model ./wiki1M_model.keyvi | hashcat -m 1000 -O -D 2 -w 4 --status --status-timer=60 --username -r ./rephraserBasic8.rule -r ~/travco_princev8.rule ./NTLMHashfile`

3. Profit

For future runs, you can reuse the Markov Chain model RePhraser had to make (saved to the path specified with `--model`), call rephraser with just `--model ./wiki1M_model.keyvi`. Don't worry, the finished/compiled models are a fraction (as much as 1/40th) the size of the model while it is being constructed in markovify and then compiled into a keyvi dictionary.

#### Two paragraphs to use in Company Policy / Password Guidelines:

Passphrases that are easy to remember, but exceedingly difficult to crack, are unlikely or illogical phrases of five or more words.
Adding special characters or numbers or other complexity, although not required, is better done between or inside words
(dozens of possible positions) instead of only on the beginnings or ends of passphrases.

Combinations of thematically-unrelated words like:

"diabetic unicorn TRAPPED chicago tunnel"

Can be easy to remember if you say them to yourself "A diabetic-unicorn is trapped in a Chicago tunnel" and force an attacker to have
 a large dictionary with multiple types of words (cities, structures, fantasy creatures, verbs, medical conditions) to even have a chance of
 producing your password. Using words that wouldn't typically come after each-other in a sentence also forces an attacker to use brute force to guess
 combinations of words. Although it may seem complex, a logical phrase like "Docking With The International Space Station" (six fairly-uncommon words right? holy cow!)
 is much simpler to crack to an attacker using a natural language model, because "Docking" and "Space Station" are both thematically related
 and very likely to be together in a sentence. If an attacker is using "Docking" as the first word (through pure brute-force) to generate
 a phrase, the rest of the words are a likely, if not *the most likely* combination to follow it.

#### Dependencies:

- [Markovify](https://github.com/jsvine/markovify) `pip3 install markovify` for initial creation and compilation of Markov Chains
- [Keyvi](https://github.com/KeyviDev/keyvi) `pip3 install keyvi` for efficient storage and shared-memory access by multiple processes
	 - [cmake](https://gitlab.kitware.com/cmake/cmake)  (apt package usually is `cmake`)
		 - [libboost](https://gitlab.kitware.com/cmake/cmake/issues/19402) (apt package usually is `libboost-all-dev`)
	 - [snappy](https://github.com/google/snappy) (apt package usually is `libsnappy-dev`)
- **Python 3.5+** is strongly recommended (keyvi dropped support for Python 2.7 and 3.4)

#### Other files in this repo:
- `rephraserBasic8.rule` Eight rules to alter rephraser's output into different common patterns of capitalization and spaces within hashcat
- `travco_princev8.rule` manually written ruleset for hashcat for use agaisnt passphrases (4000+ rules)
- `commonprefixes_sorted_50k.rule` ruleset made by running zxcvbn-python on the 37+ million 15+ character passphrases in the haveibeenpwnedv2 list, sorted with the most common prefixes first
- `commonsuffixes_sorted_50k.rule` ruleset made by running zxcvbn-python on the 37+ million 15+ character passphrases in the haveibeenpwnedv2 list, sorted with the most common suffixes first
