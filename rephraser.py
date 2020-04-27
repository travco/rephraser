import markovify
import keyvi
import os
import sys
from signal import signal, SIGINT, SIG_IGN
import json
import multiprocessing as mp
import argparse

BEGIN = "___BEGIN__"
END = "___END__"
DONE = "___DONE__"
undesirable_chars = [',','.',';',':','?','\'','"']
dct = None # Will contain global mappings for shared memory managed by keyvi
mpqueue = None # Will contain Queue
MAXQUEUESIZE = 100000 # Number of work items that is reasonable to have on the queue
worker_num = 0 # Will be changed before creating workers

def sigint_handler(signal_received, frame):
  # Following wrapup might not complete for minutes with 3 workers
  # for i in range(worker_num):
  #   if mpqueue:
  #     mpqueue.put([DONE, DONE, DONE], False)
  sys.stderr.write('[REPHRASER] SIGINT or CTRL-C detected. Attempting to exit gracefully...\n')
  last_work_item = mpqueue.get(block=False)
  sys.stderr.write('[REPHRASER] Next prefix in queue was: ' + repr(last_work_item)[2] + '\n')
  # Parent *should* be able to exit
  exit(0)

def sanitizeandmutateword(word):
  if word[0] in undesirable_chars:
    word = word[1:]
  if word != '':
    if word[-1] in undesirable_chars:
      word = word[0:len(word)-1]
  if len(word) > 1:
    return word[0].capitalize() + word[1:] # Preserve rest of case on capitalized acroynms, etc.
  else:
    return word.capitalize()

def collectall(state, depth, prefix):
  """
  Given a compiled dct and state, return a list of all phrases (lists) of exactly a certain length/depth in titlecase
  """
  completedchains = []
  cstate_model = dct[' '.join(state)].GetValue()
  if not prefix:
    prefix = list(state)
  if depth > 1:
    for nextword in cstate_model[0] :
      if nextword != END:
        nextstate = tuple(state[1:]) + (nextword,)
        nextreach = collectall(nextstate, depth - 1, prefix + [nextword])
        if nextreach:
          completedchains += nextreach
      # elif prefix:
      #   completedchains.append(prefix)
  else:
    # fix-up prefix words outside of loop because they won't need to be passed further
    mutated_prefix = []
    for word in prefix:
      mutated_prefix.append(sanitizeandmutateword(word))
    for nextword in cstate_model[0] :
      if nextword != END and nextword != '':
        mutated_word = sanitizeandmutateword(nextword)
        if mutated_word != '':
          completedchains.append(mutated_prefix + [mutated_word])
  return completedchains

def workercollectall(mpqueue):
  # Landing function for workers
  while True:
    try:
      arglist = mpqueue.get()
    except KeyboardInterrupt:
      break
    if len(arglist) == 3:
      state, depth, prefix = arglist
      if state == DONE:
        break
      outchains = collectall(state, depth, prefix)
      # output to STDOUT (outlist should be titlecase mutated, result should be titlecase with interspace)
      if not args.gpusaturated:
        for outlist in outchains:
          # Titlecase with spaces
          print(' '.join(outlist))
      else:
        for outlist in outchains:
          # Titlecase with spaces
          print(' '.join(outlist))
          # Titlecase without spaces
          print(''.join(outlist))
          # Lowercase with spaces
          print(' '.join(outlist).lower())
          # Lowercase without spaces
          print(''.join(outlist).lower())
          # First letter capitalized with spaces
          print(outlist[0] + ' ' + ' '.join(outlist[1:]).lower())
          # First letter capitalized without spaces
          print(outlist[0] + ''.join(outlist[1:]).lower())
          # Camelcase with spaces
          print(outlist[0].lower() + ' ' + ' '.join(outlist[1:]))
          # Camelcase without spaces
          print(outlist[0].lower() + ''.join(outlist[1:]))

def traverselikely(mpqueue, state, depthremaining, batchdepth, prefix):
  if not prefix:
    prefix = []
  # stateweights = [[weight, index], [weight, index]]
  stateweights = []
  # Sort and traverse from at least the most common start-points
  cstate_model = dct[' '.join(state)].GetValue()
  for i in range(len(cstate_model[1])) :
    if i == 0:
      stateweights.append([cstate_model[1][i], 0])
    else:
      stateweights.append([cstate_model[1][i] - cstate_model[1][i-1], i])
  stateweights.sort(reverse=True)

  if depthremaining <= batchdepth:
    for weighted in stateweights:
      # cstate_model[0 = words][wordindex]
      nextword = cstate_model[0][weighted[1]]
      if nextword == END:
        continue
      nextstate = tuple(state[1:]) + (nextword,)
      # Parallelize below batchdepth
      mpqueue.put([nextstate, depthremaining - 1, prefix + [nextword]])
  else:
    for weighted in stateweights:
      # dct[state][0 = words][wordindex]
      nextword = cstate_model[0][weighted[1]]
      if nextword == END:
        continue
      nextstate = tuple(state[1:]) + (nextword,)
      traverselikely(mpqueue, nextstate, depthremaining - 1, batchdepth, prefix + [nextword])

if __name__ == '__main__':
  parser = argparse.ArgumentParser(prog='rephraser.py', 
    description='Program for taking in either a model or corpus, and outputting markov chains of a specified word-length',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--model', '-m', required=True, help='Path to a saved model (make sure to set --ngrams if using 3grams) or where to save the model generated', default='')
  parser.add_argument('--ngrams', '-g', type=int, help='Number of words (n-grams) that make up a state in the Markov model, suggested 2 for large corpuses where the resulting model size might overrun RAM, 3 for best linguistic accuracy on smaller corpuses', default=2)
  parser.add_argument('--corpus', '-c', help='Path to a corpus (file with sentances) to convert into a Markov model', default='')
  parser.add_argument('--corpusisdir','-d', action='store_true', help='Handle the "--corpus" path as a directory, and create a model by walking all files inside', default=False)
  parser.add_argument('--words', '-w', type=int, help='Number of words in outputtable candidates', default=4)
  parser.add_argument('--workers', '-x', type=int, help='Manually specify the number of workers', default=(mp.cpu_count() - 1))
  parser.add_argument('--freqlist', '-f', help='Path to a frequency list of *lowercase words*, one per line (E.g. Google 10k most common words), to use as start words. Warning: This is a n^2 operation, and may take a couple minutes to find all chain start-points (in order) depending on model * freqlist size.', default='')
  parser.add_argument('--gpusaturated', '-s', action='store_true', help='If hashcat is liable to be saturated, create "Basic8" permutations in the CPU workers, usually nets an extra 7\% performance on fast hashes', default=False)
  parser.add_argument('--batchdepth', '-b', type=int, help='Number of ending words/recursions that should be handled in bulk by performing "collectall"', default=3)

  args = parser.parse_args()

  # Sanity checks, and model load/creation
  if args.corpus != '' and args.model != '':
    if args.corpusisdir and os.path.isdir(args.corpus):
      # Load multi-file corpus from --corpus
      combined_model = None
      for (dirpath, _, filenames) in os.walk(args.corpus):
        for filename in filenames:
          sys.stderr.write('[REPHRASER] Loading ' + os.path.join(dirpath, filename) + ' ...')
          with open(os.path.join(dirpath, filename)) as f:
            mmodel = markovify.Text(f, retain_original=False, state_size=args.ngrams)
            if combined_model:
              sys.stderr.write('[REPHRASER] Combining ' + os.path.join(dirpath, filename) + ' ...')
              combined_model = markovify.combine(models=[combined_model, mmodel])
            else:
              combined_model = mmodel
      del mmodel
      combined_model.compile(inplace = True)
      keyvicompiler = keyvi.JsonDictionaryCompiler()
      for key in combined_model.chain.model:
        keyvicompiler.Add(' '.join(key), json.dumps(combined_model.chain.model[key]))
      del combined_model
      keyvicompiler.Compile()
      keyvicompiler.WriteToFile(args.model)
      del keyvicompiler
      dct = keyvi.Dictionary(args.model)
    elif os.path.isfile(args.corpus):
      # Load single-file corpus from --corpus
      with open(args.corpus) as f:
        mmodel = markovify.Text(f, retain_original=False, state_size=args.ngrams)
      mmodel.compile(inplace = True)
      keyvicompiler = keyvi.JsonDictionaryCompiler()
      for key in mmodel.chain.model:
        keyvicompiler.Add(' '.join(key), json.dumps(mmodel.chain.model[key]))
      del mmodel
      keyvicompiler.Compile()
      keyvicompiler.WriteToFile(args.model)
      del keyvicompiler
      dct = keyvi.Dictionary(args.model)
  elif args.model != '':
    # Load a saved model in a keyvi file
    if os.path.isfile(args.model):
      with open(args.model) as f:
        dct = keyvi.Dictionary(args.model)
    else:
      sys.stderr.write('[REPHRASER] Couldn\'t find model at ' + args.model + '\n[REPHRASER] Exiting!\n')
      sys.exit(1)
  else:
    sys.stderr.write('[REPHRASER] You must specify either a corpus to scan and a model path to save in, or a pre-compiled model to load!\n[REPHRASER] Exiting!\n')
    sys.exit(1)

  if args.workers < 1:
    worker_num  = 1
  else:
    worker_num = args.workers

  mpqueue = mp.Queue(MAXQUEUESIZE)
  # Spin up workers once and early
  worker_processes = []
  for i in range(worker_num):
    worker = mp.Process(target=workercollectall, args=((mpqueue),))
    worker.daemon = True
    worker.start()
    worker_processes.append(worker)

  # Change signal handling in only parent
  signal(SIGINT, sigint_handler)
  if args.freqlist != '':
    # Iterate on most-frequently used words input, as long as they in the model
    freqlist = []
    if os.path.isfile(args.freqlist):
      with open(args.freqlist) as f:
        freqlist = f.read().split('\n')
    else:
      sys.stderr.write('[REPHRASER] Couldn\'t find freqlist at ' + args.freqlist + '\n[REPHRASER] Exiting!\n')
      sys.exit(1)
    
    freqtuplelists = []
    # Create array of arrays to hold keys corresponding to words in freqlist
    for i in freqlist:
      freqtuplelists.append([])
    # Iterate through all markov chain keys, keeping those that are in our freqlist, in the order of freqlist
    for key in dct.GetAllKeys():
      if key == ' '.join((BEGIN,BEGIN)) or key == ' '.join((BEGIN,BEGIN,BEGIN)):
        continue
      if END in key:
        continue
      tuplekey = tuple(key.split(' ', args.ngrams - 1))
      if args.ngrams > 2 and BEGIN in tuplekey[1]:
        try:
          foundindex = freqlist.index(tuplekey[2].lower())
          freqtuplelists[foundindex].append(tuplekey)
        except ValueError as e:
          pass
      elif BEGIN in tuplekey[0]:
        try:
          foundindex = freqlist.index(tuplekey[1].lower())
          freqtuplelists[foundindex].append(tuplekey)
        except ValueError as e:
          pass
      else:
        try:
          foundindex = freqlist.index(tuplekey[0].lower())
          freqtuplelists[foundindex].append(tuplekey)
        except ValueError as e:
          pass
    # No need for freqlist this point onward
    del freqlist
    # Iterate on keys, handling the indicated keys only
    for freqtuplelist in freqtuplelists:
      if not freqtuplelist:
        continue
      for tuplekey in freqtuplelist:
        prefix = list(tuplekey)
        prefixmod = args.ngrams
        if tuplekey[0] == BEGIN:
          prefixmod = args.ngrams - 1
          prefix = list(tuplekey[1:])
        if tuplekey[1] == BEGIN and args.ngrams > 2:
          prefixmod = args.ngrams - 2
          prefix = list(tuplekey[2:])
        # Handle the common-case where the tuplekey puts us below the batchdepth
        if args.words - prefixmod <= args.batchdepth:
          mpqueue.put([tuplekey, args.words - prefixmod - 1, prefix])
        else:
          traverselikely(mpqueue, tuplekey, args.words - prefixmod, args.batchdepth, prefix)
  else:
    # Iterate on all keys in chain model, handling most likely key (start of sentance) first
    if args.ngrams == 2:
      traverselikely(mpqueue, (BEGIN,BEGIN), args.words, args.batchdepth, [])
    elif args.ngrams == 3:
      traverselikely(mpqueue, (BEGIN,BEGIN,BEGIN), args.words, args.batchdepth, [])
    for key in dct.GetAllKeys():
      if key == ' '.join((BEGIN,BEGIN)) or key == ' '.join((BEGIN,BEGIN,BEGIN)):
        continue
      # Need to convert string keys back into tuples for programmatic use
      tuplekey = tuple(key.split(' ', args.ngrams - 1))
      if END in tuplekey:
        continue
      prefix = list(tuplekey)
      prefixmod = args.ngrams
      if tuplekey[0] == BEGIN:
        prefixmod = args.ngrams - 1
        prefix = list(tuplekey[1:])
      if tuplekey[1] == BEGIN and args.ngrams > 2:
        prefixmod = args.ngrams - 2
        prefix = list(tuplekey[2:])
      # Handle the common-case where the tuplekey puts us below the batchdepth
      if args.words - prefixmod <= args.batchdepth:
        mpqueue.put([tuplekey, args.words - prefixmod - 1, prefix])
      else:
        traverselikely(mpqueue, tuplekey, args.words - prefixmod, args.batchdepth, prefix)

  # Wrap up, send end-of-work signals to workers (one each)
  for worker in worker_processes:
    mpqueue.put([DONE, DONE, DONE])

  sys.stderr.write('\n[REPHRASER] Scheduler work completed! Waiting patiently for workers to finish queued work...\n')
  # Wait for workers to empty queue and hit done signals before killing parent process.
  for worker in worker_processes:
    worker.join()