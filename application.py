import os

from cs50 import SQL
import sqlite3
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import time
import datetime
from werkzeug.utils import secure_filename

from helpers import apology, login_required, lookup, usd

from decimal import Decimal

TWOPLACES = Decimal(10) ** -2

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

UPLOAD_FOLDER = '/images'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///translev.db")

# Make sure API key is set


@app.route("/")
@login_required
def index():
    """Redirect to transactions"""

    db = SQL("sqlite:///translev.db")
    userid = session["user_id"]
    userSession = db.execute("SELECT * FROM users WHERE users.user_id = ?", userid)
    username = userSession[0]["username"]
    level = userSession[0]['type']
    group_username = userSession[0]['group_username']
    ids = [group_username, username, level]

    if level == "SUPERADMIN":
        return redirect("/balance")
    elif level == "MAKER":
        return redirect("/request_trx")
    elif level == "APPROVER":
        return redirect("/approve")
    elif level == "RELEASER":
        return redirect("/act")
    elif level == "ACCOUNTANT":
        return redirect("/journal")


@app.route("/request_trx", methods=["GET", "POST"])
@login_required
def request_trx():
    """Request transactions"""

    db = SQL("sqlite:///translev.db")
    userid = session["user_id"]
    userSession = db.execute("SELECT * FROM users WHERE users.user_id = ?", userid)
    username = userSession[0]["username"]
    level = userSession[0]['type']
    group_username = userSession[0]['group_username']
    ids = [group_username, username, level]

    if level in ["SUPERADMIN", "MAKER"]:
        if request.method == "GET":

            cashin = db.execute("SELECT * FROM cashin WHERE maker = ? AND group_username = ?", username, group_username)
            for row in cashin:
                if row["requested"] == 1:
                    row["status"] = "Waiting for approval"
                elif row["approved"] == 1:
                    row["status"] = "Approved"
                else:
                    row["status"] = "Rejected"
                if row["add_notes"] == None:
                    row["add_notes"] = ""

            accounts_all = db.execute("SELECT * FROM accounts WHERE visibility = 1 AND include = 1 AND group_username = ?", \
            group_username)
            accounts = list(set([i["acc_com"] for i in accounts_all]))

            trx = db.execute("SELECT * FROM trx WHERE maker = ? AND group_username = ?", username, group_username)
            for row in trx:
                if row["requested"] == 1:
                    row["status"] = "Waiting for Approval"
                elif row["approved"] == 1:
                    row["status"] = "Approved"
                else:
                    row["status"] = "Rejected"
                if row["add_notes"] == None:
                    row["add_notes"] = ""

            return render_template("request.html", trx=trx, ids=ids, cashin=cashin, accounts=accounts)

        else:
            if request.form.get("amount2") == None:
                amount = int(request.form.get("amount"))
                notes = request.form.get("notes")
                method = request.form.get("method")
                dest_entity = request.form.get("dest_entity")
                dest_account = request.form.get("dest_account")
                dest_account_no = request.form.get("dest_account_no")
                db.execute("INSERT INTO trx (maker, value, notes, req_method, dest_entity, dest_account, dest_account_no, group_username) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", \
                            username, amount, notes, method, dest_entity, dest_account, dest_account_no, group_username)
                flash("Transaction request entered!")
                return redirect("/request_trx")
            else:
                amount = int(request.form.get("amount2"))
                notes = request.form.get("notes2")
                accounts = request.form.get("account2").split(" - ")
                company = accounts[0]
                account = accounts[1]
                db.execute("INSERT INTO cashin (maker, value, notes, debit_com, debit_acc, group_username) VALUES (?, ?, ?, ?, ?, ?)", \
                            username, amount, notes, company, account, group_username)
                flash("Cash in request entered!")
                return redirect("/request_trx")
    else:
        flash("You are not MAKER / SUPER ADMIN!")
        return redirect("/")

@app.route("/approve", methods=["GET", "POST"])
@login_required
def approve():
    """Show all transactions need to approve"""

    db = SQL("sqlite:///translev.db")
    userid = session["user_id"]
    userSession = db.execute("SELECT * FROM users WHERE users.user_id = ?", userid)
    username = userSession[0]["username"]
    level = userSession[0]['type']
    group_username = userSession[0]['group_username']
    ids = [group_username, username, level]

    if level in ["SUPERADMIN", "APPROVER"]:
        if request.method == "GET":
            trx = db.execute("SELECT * FROM trx WHERE requested = 1 AND group_username = ?", group_username)
            trx2 = db.execute("SELECT * FROM trx WHERE approved = 1 AND group_username = ?", group_username)
            accounts = db.execute("SELECT * FROM accounts WHERE visibility = 1 AND group_username = ?", group_username)

            cashin = db.execute("SELECT * FROM cashin WHERE requested = 1 AND group_username = ?", group_username)
            for i in cashin:
                com = i["debit_com"]
                acc = i["debit_acc"]
                balance_now = db.execute("SELECT * FROM accounts WHERE visibility = 1 AND group_username = ? \
                AND acc_name = ? AND com_name = ?", group_username, acc, com)[0]["balance"]
                i["balance_after"] = balance_now + i["value"]

            cashin2 = db.execute("SELECT * FROM cashin WHERE approved = 1 AND group_username = ?", group_username)

            return render_template("approve.html", accounts=accounts, trx=trx, trx2=trx2, ids=ids, \
            cashin=cashin, cashin2=cashin2)
        else:
            if request.form.get("csh_id") == None:
                trx_id = int(request.form.get("trx_id")[4:])
                add_notes = request.form.get("add_notes")
                ts = time.time()
                timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

                if request.form.get("button") == "accept":
                    debit = request.form.get("debit").split(" - ")
                    credit = request.form.get("credit").split(" - ")

                    trx_ = db.execute("SELECT * FROM trx WHERE trx_id = ?", trx_id)
                    acc_ = db.execute("SELECT * FROM accounts WHERE com_name = ? AND acc_name = ? AND group_username = ?", \
                    credit[0], credit[1], group_username)

                    if acc_[0]["balance"] >= trx_[0]["value"]:
                        db.execute("UPDATE trx SET debit_com = ?, debit_acc = ?, credit_com = ?, credit_acc = ?, approver = ?, \
                                    approved_date = ?, approved = ?, requested = ?, add_notes = ? WHERE trx_id = ?", \
                                    debit[0], debit[1], credit[0], credit[1], username, timestamp, 1, 0, add_notes, trx_id)

                        flash("Transaction request approved!")
                        return redirect("/approve")

                    else:
                        flash("Not enough balance in the credit account!")
                        return redirect("/approve")

                else:
                    db.execute("UPDATE trx SET approver = ?, rejected_date = ?, rejected = ?, requested = ?, add_notes = ? \
                    WHERE trx_id = ?", username, timestamp, 1, 0, add_notes, trx_id)
                    flash("Transaction request rejected!")
                    return redirect("/approve")

            else:
                csh_id = int(request.form.get("csh_id")[4:])
                add_notes = request.form.get("add_notes")

                csh_ = db.execute("SELECT * FROM cashin WHERE cash_id = ?", csh_id)
                company = csh_[0]["debit_com"]
                account = csh_[0]["debit_acc"]
                value_csh = csh_[0]["value"]


                ts = time.time()
                timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

                if request.form.get("button") == "accept":
                    db.execute("UPDATE cashin SET approver = ?, approved_date = ?, approved = ?, requested = ?, add_notes= ? WHERE cash_id = ?", \
                                username, timestamp, 1, 0, add_notes, csh_id)

                    acc_ = db.execute("SELECT * FROM accounts WHERE acc_name = ? AND com_name = ? AND group_username = ?", \
                    account, company, group_username)
                    value_bal = acc_[0]["balance"]
                    value_bal = value_bal + value_csh

                    db.execute("UPDATE accounts SET balance = ? WHERE com_name = ? AND acc_name = ? AND group_username = ?", \
                    value_bal, company, account, group_username)

                    flash("Cash in request approved!")
                    return redirect("/approve")
                else:
                    db.execute("UPDATE cashin SET approver = ?, rejected_date = ?, rejected = ?, requested = ?, add_notes = ? \
                    WHERE cash_id = ?", username, timestamp, 1, 0, add_notes, csh_id)
                    flash("Cash in request rejected!")
                    return redirect("/approve")
    else:
        flash("You are not APPROVER / SUPER ADMIN!")
        return redirect("/")


@app.route("/act", methods=["GET", "POST"])
@login_required
def act():
    """Show all transactions need to approve"""

    db = SQL("sqlite:///translev.db")
    userid = session["user_id"]
    userSession = db.execute("SELECT * FROM users WHERE users.user_id = ?", userid)
    username = userSession[0]["username"]
    level = userSession[0]['type']
    group_username = userSession[0]['group_username']
    ids = [group_username, username, level]

    if level in ["SUPERADMIN", "RELEASER"]:
        if request.method == "GET":
            trx = db.execute("SELECT * FROM trx WHERE approved = 1 AND acted = 0 AND group_username = ?", group_username)
            trx2 = db.execute("SELECT * FROM trx WHERE acted = 1 AND group_username = ?", group_username)

            return render_template("act.html", trx=trx, trx2=trx2, ids=ids)
        else:
            trx_id = int(request.form.get("trx_id")[4:])

            ts = time.time()
            timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

            db.execute("UPDATE trx SET actor = ?, acted_date = ?, acted = ? WHERE trx_id = ?", \
                        username, timestamp, 1, trx_id)

            trx_ = db.execute("SELECT * FROM trx WHERE trx_id = ?", trx_id)
            credit_company = trx_[0]["credit_com"]
            credit_account = trx_[0]["credit_acc"]
            debit_company = trx_[0]["debit_com"]
            debit_account = trx_[0]["debit_acc"]
            value_trx = trx_[0]["value"]

            acc_ = db.execute("SELECT * FROM accounts WHERE acc_name = ? AND com_name = ? AND group_username = ?", \
            credit_account, credit_company, group_username)
            value_bal = acc_[0]["balance"]
            value_bal = value_bal - value_trx

            db.execute("UPDATE accounts SET balance = ? WHERE com_name = ? AND acc_name = ? AND group_username = ?", \
            value_bal, credit_company, credit_account, group_username)

            acc_2 = db.execute("SELECT * FROM accounts WHERE acc_name = ? AND com_name = ? AND group_username = ?", \
            debit_account, debit_company, group_username)
            value_bal2 = acc_2[0]["balance"]
            value_bal2 = value_bal2 + value_trx

            db.execute("UPDATE accounts SET balance = ? WHERE com_name = ? AND acc_name = ? AND group_username = ?", \
            value_bal2, debit_company, debit_account, group_username)

            flash("Transaction done!")
            return redirect("/act")
    else:
        flash("You are not RELEASER / SUPER ADMIN!")
        return redirect("/")


@app.route("/journal", methods=["GET", "POST"])
@login_required
def journal():
    """Show all transactions need to approve"""

    db = SQL("sqlite:///translev.db")
    userid = session["user_id"]
    userSession = db.execute("SELECT * FROM users WHERE users.user_id = ?", userid)
    username = userSession[0]["username"]
    level = userSession[0]['type']
    group_username = userSession[0]['group_username']
    ids = [group_username, username, level]

    if level in ["SUPERADMIN", "ACCOUNTANT"]:
        if request.method == "GET":
            trx = db.execute("SELECT * FROM trx WHERE acted = 1 AND journaled = 0 AND group_username = ?", group_username)
            trx2 = db.execute("SELECT * FROM trx WHERE journaled = 1 AND group_username = ?", group_username)

            return render_template("journal.html", trx=trx, trx2=trx2, ids=ids)
        else:
            trx_id = request.form.getlist("trx_")
            print(trx_id)
            ts = time.time()
            timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

            if len(trx_id) == 0:
                flash("No transaction(s) journaled!")
                return redirect("/journal")

            for i in trx_id:
                db.execute("UPDATE trx SET journaler = ?, journaled_date = ?, journaled = ? WHERE trx_id = ?", \
                            username, timestamp, 1, i)

            flash("Transaction(s) journaled!")
            return redirect("/journal")
    else:
        flash("You are not ACCOUNTANT / SUPER ADMIN!")
        return redirect("/")


@app.route("/accounts", methods=["GET", "POST"])
@login_required
def accounts():
    """Add and shows accounts"""

    db = SQL("sqlite:///translev.db")
    userid = session["user_id"]
    userSession = db.execute("SELECT * FROM users WHERE users.user_id = ?", userid)
    username = userSession[0]["username"]
    level = userSession[0]['type']
    group_username = userSession[0]['group_username']
    ids = [group_username, username, level]

    if level in ["SUPERADMIN"]:
        if request.method == "GET":
            rows = db.execute("SELECT * FROM accounts WHERE visibility = 1 AND group_username = ?", group_username)
            for id_,row in zip(list(range(1,len(rows)+1)),rows):
                row["acc_id"] = id_
            return render_template("accounts.html", rows=rows, ids=ids)

        else:
            acc_name = request.form.get("acc_name")
            com_name = request.form.get("com_name")
            init_value = request.form.get("init_value")
            if init_value in [None, ""]:
                init_value = 0
            include = request.form.get("include")
            if include == "Yes":
                include = 1
            else:
                include = 0
            acc_com = com_name + " - " + acc_name
            rows = db.execute("SELECT * FROM accounts WHERE LOWER(acc_com) = ? AND visibility = 1 \
                               AND group_username = ?", acc_com.lower(), group_username)
            if len(rows) > 0:
                flash("Account already exist!")
                rows = db.execute("SELECT * FROM accounts WHERE visibility = 1 AND group_username = ?", group_username)
                for id_,row in zip(list(range(1,len(rows)+1)),rows):
                    row["acc_id"] = id_
                return render_template("accounts.html", rows=rows, ids=ids)
            else:
                db.execute("INSERT INTO accounts (acc_name, com_name, acc_com, include, group_username, balance) \
                VALUES (?, ?, ?, ?, ?, ?)", acc_name.upper(), com_name.upper(), acc_com.upper(), include, group_username, init_value)
                rows = db.execute("SELECT * FROM accounts WHERE visibility = 1 AND group_username = ?", group_username)
                for id_,row in zip(list(range(1,len(rows)+1)),rows):
                    row["acc_id"] = id_
                flash("Account added!")
                return render_template("accounts.html", rows=rows, ids=ids)
    else:
        flash("You are not SUPER ADMIN!")
        return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    db = SQL("sqlite:///translev.db")

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username AND allowed = 1",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid username and/or password!")
            return render_template("login.html")

        # Remember which user has logged in
        session["user_id"] = rows[0]["user_id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    db = SQL("sqlite:///translev.db")

    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        group_username = request.form.get("group_username")
        user_type = "SUPERADMIN"

        usernames = db.execute("SELECT * FROM users WHERE username = ? OR group_username = ?", \
                                username, group_username)

        if group_username == "":
            flash("You must provide group username!")
            return redirect("/register")

        if username == "":
            flash("You must provide username!")
            return redirect("/register")

        if len(usernames) > 0:
            flash("Username already exist / your group already has super admin!")
            return redirect("/register")

        password = request.form.get("password")

        if password == "":
            flash("You must provide password!")
            return redirect("/register")

        password2 = request.form.get("password2")

        if password != password2:
            flash("Passwords don't match!")
            return redirect("/register")

        passwordHash = generate_password_hash(password)

        db.execute("INSERT INTO users (group_username, username, hash, type) VALUES (?, ?, ?, ?)", \
                    group_username, username, passwordHash, user_type)

        return login()


@app.route("/balance")
@login_required
def balance():
    """Show balance"""

    db = SQL("sqlite:///translev.db")
    userid = session["user_id"]
    userSession = db.execute("SELECT * FROM users WHERE users.user_id = ?", userid)
    username = userSession[0]["username"]
    level = userSession[0]['type']
    group_username = userSession[0]['group_username']
    ids = [group_username, username, level]

    if level in ["SUPERADMIN", "RELEASER", "APPROVER"]:
        balances = db.execute("SELECT * FROM accounts WHERE group_username = ? AND include = 1", group_username)
        for i, row in zip(list(range(1,len(balances)+1)), balances):
            row['acc_id'] = i

        return render_template("balance.html", balances=balances, ids=ids)
    else:
        flash("You are not APPROVER / RELEASER / SUPER ADMIN!")
        return redirect("/")

@app.route("/users", methods=["GET", "POST"])
@login_required
def users():
    """Show users"""

    db = SQL("sqlite:///translev.db")
    userid = session["user_id"]
    userSession = db.execute("SELECT * FROM users WHERE users.user_id = ?", userid)
    username = userSession[0]["username"]
    level = userSession[0]['type']
    group_username = userSession[0]['group_username']
    ids = [group_username, username, level]

    if level in ["SUPERADMIN"]:
        if request.method == "GET":
            users = db.execute("SELECT * FROM users WHERE allowed = 1 AND group_username = ?", group_username)
            for id_,row in zip(list(range(1,len(users)+1)),users):
                row["user_id"] = id_
            return render_template("users.html", users=users, ids=ids)
        else:
            username = request.form.get("username")
            user_type = request.form.get("user_type")

            usernames = db.execute("SELECT * FROM users WHERE username = ?", username)

            if len(usernames) > 0:
                flash("Username already exist!")
                return redirect("/users")

            password = request.form.get("password")
            password2 = request.form.get("password2")

            if password != password2:
                flash("Passwords don't match!")
                return redirect("/users")

            passwordHash = generate_password_hash(password)

            db.execute("INSERT INTO users (group_username, username, hash, type) VALUES (?, ?, ?, ?)", \
                        group_username, username, passwordHash, user_type)

            return redirect("/users")
    else:
        flash("You are not SUPER ADMIN")
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
