import numpy as np

vals = []

inside = False

with open("eeprom.txt", "r") as f:
    for line in f:
        line = line.strip()

        if line == "<EEPROM_BEGIN>":
            inside = True
            continue

        if line == "<EEPROM_END>":
            break

        if inside:
            vals.append(int(line))

arr = np.array(vals, dtype=np.uint16)

print("WORDS:", len(arr))

arr.tofile("eeprom.bin")

print("Saved eeprom.bin")
