import random
import re

# --------------------------------------------------------
# HARD-CODED CONFIG (you only change TARGET_REGEX)
# --------------------------------------------------------
TARGET_REGEX = r"^a(?:a|b)*a$"        # <--- PUT YOUR TARGET REGEX HERE
ALPHABET = ["a", "b"]              # strict: only two symbols allowed
NUM_POS = 300                      # number of positive samples
NUM_NEG = 300                      # number of negative samples
MIN_LEN = 0                        # minimum string length
MAX_LEN = 20                       # maximum string length
HARD_NEG_FRAC = 0.4                # percent of negatives as near-miss
RANDOM_SEED = 42
# --------------------------------------------------------

random.seed(RANDOM_SEED)
pattern = re.compile(TARGET_REGEX)


# --------------------------------------------------------
# Utility: generate random string over alphabet {a,b}
# --------------------------------------------------------
def random_string():
    length = random.randint(MIN_LEN, MAX_LEN)
    return "".join(random.choice(ALPHABET) for _ in range(length))


# --------------------------------------------------------
# Mutations to create hard “near-miss” negatives
# --------------------------------------------------------
def mutate_substitute(s):
    if not s:
        return random.choice(ALPHABET)
    i = random.randrange(len(s))
    alt = "a" if s[i] == "b" else "b"
    return s[:i] + alt + s[i+1:]

def mutate_insert(s):
    i = random.randrange(len(s) + 1)
    return s[:i] + random.choice(ALPHABET) + s[i:]

def mutate_delete(s):
    if not s:
        return ""
    i = random.randrange(len(s))
    return s[:i] + s[i+1:]

def mutate_swap(s):
    if len(s) < 2:
        return s
    i = random.randrange(len(s) - 1)
    return s[:i] + s[i+1] + s[i] + s[i+2:]

# Pick random 1–2 edits
def hard_negative(s):
    ops = [mutate_substitute, mutate_insert, mutate_delete, mutate_swap]
    for _ in range(random.choice([1, 2])):
        s = random.choice(ops)(s)
    return s


# --------------------------------------------------------
# Generate POSITIVES — strings that match regex completely
# --------------------------------------------------------
positives = set()
attempts = 0
max_attempts = 200000

while len(positives) < NUM_POS and attempts < max_attempts:
    s = random_string()
    if pattern.fullmatch(s):
        positives.add(s)
    attempts += 1

if len(positives) < NUM_POS:
    print(f"WARNING: Only found {len(positives)} positives.")


# --------------------------------------------------------
# Generate NEGATIVES — mix of hard and random negatives
# --------------------------------------------------------
negatives = set()
target_hard = int(NUM_NEG * HARD_NEG_FRAC)

# 1) Hard negatives from positives
pos_list = list(positives) if positives else ["a"]
i = 0
guard = 0

while len(negatives) < target_hard and guard < NUM_NEG * 50:
    base = pos_list[i % len(pos_list)]
    cand = hard_negative(base)
    if MIN_LEN <= len(cand) <= MAX_LEN and not pattern.fullmatch(cand):
        negatives.add(cand)
    i += 1
    guard += 1

# 2) Random negatives
attempts = 0
while len(negatives) < NUM_NEG and attempts < max_attempts:
    s = random_string()
    if not pattern.fullmatch(s):
        negatives.add(s)
    attempts += 1

if len(negatives) < NUM_NEG:
    print(f"WARNING: Only found {len(negatives)} negatives.")


# --------------------------------------------------------
# Write output files
# --------------------------------------------------------
with open("good.txt", "w") as g:
    for s in sorted(positives, key=lambda x: (len(x), x)):
        g.write(s + "\n")

with open("bad.txt", "w") as b:
    for s in sorted(negatives, key=lambda x: (len(x), x)):
        b.write(s + "\n")

print("Dataset generation finished!")
print(f"Wrote good.txt : {len(positives)} samples")
print(f"Wrote bad.txt  : {len(negatives)} samples")
print(f"Regex used: {TARGET_REGEX}")
