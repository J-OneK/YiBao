def f(x):
    x.append(1)

a = []
f(a)
print(a)   # [1]
