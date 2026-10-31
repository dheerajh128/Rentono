if(process.env.NODE_ENV != "production"){
    require("dotenv").config();
}


const express = require("express");
const app = express();
const methodOverride = require("method-override");
const path = require("path");
const mongoose = require("mongoose");

const dbUrl = process.env.ATLAS_URL;
const ExpressError = require("./utilities/ExpressError.js")
const ejsMate = require("ejs-mate");
const session = require("express-session");
const MongoStore = require("connect-mongo").default;
const flash = require("connect-flash");
const passport = require("passport");
require("./config/passport.js");
const dns = require("dns");
dns.setServers([
    '1.1.1.1',
    '8.8.8.8'
])

const listingsRoute = require("./routes/listings.js")
const reviewsRoute = require("./routes/reviews.js")
const usersRoute = require("./routes/users.js")

app.set("views",path.join(__dirname,"/views"));
app.set("view engine","ejs");
app.use(express.urlencoded({extended:true}));
app.use(express.static(path.join(__dirname,"/public")));
app.use(methodOverride("_method"));
app.engine("ejs",ejsMate);


main().then(()=>{
    console.log("Connected To DB");
}).catch((err)=>{
    console.log(err);
})

async function main(){
    await mongoose.connect(dbUrl);
}

const store = MongoStore.create({
    mongoUrl : dbUrl,
    crypto :{
        secret : process.env.SECRET
    },
    touchAfter: 24*60*60
});

store.on("error",()=>{
    console.log("ERROR IN THE DATABASE");
})

const sessionOptions = {
    store,
    secret :process.env.SECRET,
    resave:false,
    saveUninitialized:true,
    cookie :{
        expires : Date.now() + 7*24*60*60*1000,
        maxAge : 7*24*60*60*1000,
        httpOnly : true
    }
};

app.use(session(sessionOptions));
app.use(flash());

app.use(passport.initialize());
app.use(passport.session());


app.use((req,res,next)=>{
    res.locals.success = req.flash("success");
    res.locals.error = req.flash("error");
    res.locals.currentUser = req.user;
    next();
})

app.get("/",(req,res)=>{
    req.flash("success","Welcome to Rentono")
    res.redirect("/listings");
})

app.use("/listings",listingsRoute)
app.use("/listings/:id/reviews",reviewsRoute)
app.use("/",usersRoute)

app.use((req,res,next)=>{
    next(new ExpressError(404,"Page not found!"));
})

app.use((err,req,res,next)=>{
    console.log(err); 
    let {status = 500,message = "Something went wrong "} = err;
    // res.status(status).send(message);
    res.status(status).render("error.ejs",{message});
})



app.listen(8080,()=>{
    console.log("app is listening");
})