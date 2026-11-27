"use strict";
const BFVault = (() => {
 const iterations=310000;
 const encode=bytes=>btoa(String.fromCharCode(...bytes));
 const decode=value=>Uint8Array.from(atob(value),c=>c.charCodeAt(0));
 async function keyFor(password,salt) {
  if(typeof password!=="string" || password.length<10 || password.length>256) throw new Error("PASSWORD_LENGTH");
  const material=await crypto.subtle.importKey("raw",new TextEncoder().encode(password),"PBKDF2",false,["deriveKey"]);
  return crypto.subtle.deriveKey({name:"PBKDF2",salt,iterations,hash:"SHA-256"},material,
    {name:"AES-GCM",length:256},false,["encrypt","decrypt"]);
 }
 async function encrypt(profile,password) {
  const salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
  const key=await keyFor(password,salt);
  const ciphertext=await crypto.subtle.encrypt({name:"AES-GCM",iv},key,new TextEncoder().encode(JSON.stringify(profile)));
  return {version:2,algorithm:"AES-GCM",kdf:"PBKDF2-SHA256",iterations,salt:encode(salt),iv:encode(iv),ciphertext:encode(new Uint8Array(ciphertext))};
 }
 async function decrypt(envelope,password) {
  if(!envelope || envelope.version!==2 || envelope.algorithm!=="AES-GCM" || envelope.kdf!=="PBKDF2-SHA256" ||
     envelope.iterations!==iterations || typeof envelope.ciphertext!=="string" || envelope.ciphertext.length>40000 ||
     typeof envelope.salt!=="string" || envelope.salt.length!==24 || typeof envelope.iv!=="string" || envelope.iv.length!==16) throw new Error("INVALID_VAULT");
  const salt=decode(envelope.salt),iv=decode(envelope.iv);
  if(salt.length!==16 || iv.length!==12) throw new Error("INVALID_VAULT");
  const key=await keyFor(password,salt);
  const plaintext=await crypto.subtle.decrypt({name:"AES-GCM",iv},key,decode(envelope.ciphertext));
  return JSON.parse(new TextDecoder().decode(plaintext));
 }
 return {encrypt,decrypt};
})();
if(typeof module!=="undefined" && module.exports) module.exports=BFVault;
