const express = require("express");
const router = express.Router();
const wrapAsync = require("../utilities/wrapAsync.js");
const passport = require("passport");

const {saveRedirectUrl} = require("../middleware.js");
const { signup, renderSignup, renderLogin, logout, login } = require("../controllers/users.js");

router.get("/signup", renderSignup);

router.post("/signup",wrapAsync(signup));

router.get("/login",renderLogin);

router.post("/login",saveRedirectUrl,passport.authenticate("local",{
    failureRedirect : "/login",
    failureFlash : true}),login);

router.get("/logout",logout);


module.exports = router;