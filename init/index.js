const mongoose = require("mongoose");
const Listing = require("../models/listing.js")
const MONGO_URL = "mongodb://127.0.0.1:27017/rentono";
const initData = require("./dbss.js");

main().then(()=>{
    console.log("Connected To DB");
}).catch((err)=>{
    console.log(err);
})

async function main(){
    await mongoose.connect(MONGO_URL);
}

const init = async ()=>{
    await Listing.deleteMany({});
    initData.data = initData.data.map((obj)=>({...obj,owner: new mongoose.Types.ObjectId('694444b80dc64854ccc86f0b')
}));
    await Listing.insertMany(initData.data);
}
init();