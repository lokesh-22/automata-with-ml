import random
import re

TARGET_REGEX = r"^a(?:a|b)*a$"       
ALPHABET = ["a", "b"]            
NUM_POS = 300                     
NUM_NEG = 300                     
MIN_LEN = 0                       
MAX_LEN = 20                      
HARD_NEG_FRAC = 0.4               
RANDOM_SEED = 42

random.seed(RANDOM_SEED)
pattern = re.compile(TARGET_REGEX)

def random_string():
    length = random.randint(MIN_LEN, MAX_LEN)
    return "".join(random.choice(ALPHABET) for _ in range(length))

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

def hard_negative(s):
    ops = [mutate_substitute, mutate_insert, mutate_delete, mutate_swap]
    for _ in range(random.choice([1, 2])):
        s = random.choice(ops)(s)
    return s


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

negatives = set()
target_hard = int(NUM_NEG * HARD_NEG_FRAC)

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

attempts = 0
while len(negatives) < NUM_NEG and attempts < max_attempts:
    s = random_string()
    if not pattern.fullmatch(s):
        negatives.add(s)
    attempts += 1

if len(negatives) < NUM_NEG:
    print(f"WARNING: Only found {len(negatives)} negatives.")

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
