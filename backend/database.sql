CREATE DATABASE IF NOT EXISTS public_opinion;


USE public_opinion;


CREATE TABLE users(

id BIGINT PRIMARY KEY AUTO_INCREMENT,

username VARCHAR(50) NOT NULL UNIQUE,

nickname VARCHAR(50) NOT NULL,

password VARCHAR(255) NOT NULL,

preferences JSON

);
