const User = require("../models/user.js");


module.exports.renderSignup =(req,res)=>{
    res.render("users/signup.ejs");
}

module.exports.signup = async (req,res)=>{
    try{
        let {username,email,password} = req.body;
        let newUser = new User({email,username});
        const registeredUser = await User.register(newUser,password);
        req.login(registeredUser,(err)=>{
            if(err){
                return next(err);
            }
            req.flash("success","Welcome to Rentono");
            res.redirect("/listings");
        })
    }catch(e){
        req.flash("error",e.message);
        res.redirect("/signup");
    }
}

module.exports.renderLogin = (req,res)=>{
    res.render("users/login.ejs");
}

module.exports.login = async (req,res)=>{
    req.flash("success","Welcome Back!! You are logged in.")
    let redirectUrl = res.locals.RedirectUrl || "/listings";
    res.redirect(redirectUrl);
}


module.exports.logout = (req,res,next)=>{
    req.logout((err)=>{
        if(err){
            return  next(err);
        }
        req.flash("success","You are Logged Out");
        res.redirect("/listings")
    })
}