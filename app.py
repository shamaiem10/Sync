from flask import Flask,request,render_template,session,url_for,Response,redirect


app=Flask(__name__)
app.secret_key='syn'
@app.route('/',methods=['POST','GET'])
def login():
    if request.method=='POST':
        username=request.form.get('username')
        session['user']=username
        password=request.form.get('password')
        if username=='shamaiem' and password=='shamaiem':
            return render_template('home.html',name=username)
        else:
            redirect('/')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)  
    return redirect(url_for('login')) 


if __name__=='__main__':
    app.run(debug=True)