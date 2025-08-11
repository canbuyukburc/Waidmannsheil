package com.waidmannsheil.model;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "environments")
@Data
@NoArgsConstructor
public class Environment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(unique = true, nullable = false)
    private String name;

    @Column(unique = true, nullable = false)
    private String accessCode;  // Code for viewers to join

    @Column(unique = true, nullable = false)
    private String maintainerCode;  // Special code for maintainers to join

    @OneToMany(mappedBy = "environment", cascade = CascadeType.ALL)
    private Set<User> users = new HashSet<>();

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }
}
