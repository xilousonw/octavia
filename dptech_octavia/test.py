import pandas as pd

import base64


need_to_be_decode = "aHR0cHM6Ly93b3JtaG9sZS5hcHAvZ096elAjbXBqZFJ3TGFPLWF3czkxQWlRa1pmUSBwYXNzd29yZCBsaW5iZWkxMjM0NTY="
decoded_code = base64.b64decode(need_to_be_decode)
print(decoded_code)

encode_code = decoded_code
encode_code = base64.b64encode(decoded_code)
print(encode_code)