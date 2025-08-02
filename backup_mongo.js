const { exec } = require('child_process');
const date = new Date().toISOString().split('T')[0];

exec(`mongodump --uri="${process.env.MONGODB_URI}" --out=./backups/${date}`, 
  (error, stdout, stderr) => {
    if (error) {
      console.error(`Backup failed: ${error}`);
      return;
    }
    console.log(`Backup successful: ${date}`);
});
