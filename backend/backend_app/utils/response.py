def success(data=None,message="success"):

    return {

        "code":200,

        "message":message,

        "data":data

    }



def error(message="error",code=500):

    return {

        "code":code,

        "message":message,

        "data":None

    }