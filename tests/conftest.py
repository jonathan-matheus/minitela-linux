import os

# The tests check English strings: never pick up the developer's language. Set before
# minitela.i18n is imported, since it chooses the language once.
os.environ["LANGUAGE"] = "en"
