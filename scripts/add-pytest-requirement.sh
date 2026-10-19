import os

# add pytest to test requirements
with open('mock-backend/requirements.txt','a') as f:
    f.write('\npytest==7.4.2\n')
