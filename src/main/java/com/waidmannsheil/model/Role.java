package com.waidmannsheil.model;

public enum Role {
    ADMIN,       // Full control - can manage users and environment
    MAINTAINER,  // Can manage products
    VIEWER       // Can only view products
}
