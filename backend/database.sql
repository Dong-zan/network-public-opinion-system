CREATE DATABASE IF NOT EXISTS public_opinion;


USE public_opinion;


CREATE TABLE users(

id BIGINT PRIMARY KEY AUTO_INCREMENT,

username VARCHAR(50),

password VARCHAR(100),

preferences JSON

);