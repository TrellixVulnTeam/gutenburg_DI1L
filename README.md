# Gutenburg - A better way to consume the gutenberg book catalog  
Gutenburg generates an sqlite or json dump for use with other projects.  

I wrote this because https://pypi.org/project/Gutenberg/ takes around ~10 hours to process, and has other flaws.  
This should be simpler to use, have more data, and only take around 30-45 minutes to process.  

# User guide  
`pip install gutenburg`  
`gutenburg --sqlite ./database.db`  
The sqlite schema can be found in the source code.  
https://github.com/elitepleb/gutenburg/blob/master/gutenburg.py#L276  
  
`gutenburg --json ./data.json`  
The json schema is not too disimilar  
![Image](https://i.imgur.com/iJJecbP.png)

# Issues
Dumping a big json array is never a good idea, as non streaming libraries will take some time to open/parse the file.  
